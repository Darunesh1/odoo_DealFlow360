import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { API_URL } from "@/config"
import { api, errorMessage } from "@/lib/api"
import { tokenStore } from "@/lib/tokens"
import type {
  AlertCounts,
  DashboardData,
  DealAlert,
  ReportData,
} from "@/types/api"

export interface ReportFilters {
  from?: string
  to?: string
  rep?: string
  category?: string
}

function toQuery(filters: ReportFilters) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) search.set(key, value)
  }
  return search
}

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.get<DashboardData>("/dashboard")).data,
    // Cached 30s on the server; matching here keeps the tiles from flickering.
    staleTime: 30_000,
  })
}

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: async () => (await api.get<DealAlert[]>("/alerts")).data,
    staleTime: 15_000,
  })
}

export function useAlertCounts() {
  return useQuery({
    queryKey: ["alerts", "counts"],
    queryFn: async () => (await api.get<AlertCounts>("/alerts/counts")).data,
    staleTime: 15_000,
  })
}

export function useAlertActions() {
  const queryClient = useQueryClient()

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["alerts"] })
    queryClient.invalidateQueries({ queryKey: ["dashboard"] })
  }

  const sweep = useMutation({
    mutationFn: async () => (await api.post<AlertCounts>("/alerts/sweep")).data,
    onSuccess: (counts) => {
      refresh()
      const total =
        counts.stalled_deals + counts.discount_anomalies + counts.delivery_slippage
      toast.success(
        total === 0 ? "Nothing is at risk right now." : `${total} deals flagged.`
      )
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not run the sweep.")),
  })

  const act = useMutation({
    mutationFn: async ({
      alertId,
      action,
      note,
    }: {
      alertId: string
      action: "nudge" | "escalate" | "resolve"
      note?: string
    }) =>
      (await api.post<DealAlert>(`/alerts/${alertId}/action`, { action, note })).data,
    onSuccess: (alert) => {
      refresh()
      toast.success(
        alert.status === "resolved"
          ? "Resolved."
          : alert.status === "escalated"
            ? "Escalated to the manager."
            : "The rep has been nudged."
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not act on that alert.")),
  })

  return { sweep, act }
}

export function useReport(filters: ReportFilters) {
  return useQuery({
    queryKey: ["reports", filters],
    queryFn: async () =>
      (await api.get<ReportData>(`/reports?${toQuery(filters)}`)).data,
    staleTime: 60_000,
  })
}

/**
 * Downloads an export.
 *
 * Fetched with the bearer token rather than opened as a plain link: the export
 * routes are authenticated, and a bare href sends no Authorization header.
 */
export async function downloadReport(
  format: "xlsx" | "pdf",
  filters: ReportFilters
) {
  const token = tokenStore.getAccess()
  const response = await fetch(
    `${API_URL}/reports/export.${format}?${toQuery(filters)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  )
  if (!response.ok) {
    toast.error("Could not build that export.")
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `dealflow-sales.${format}`
  link.click()
  URL.revokeObjectURL(url)
}
