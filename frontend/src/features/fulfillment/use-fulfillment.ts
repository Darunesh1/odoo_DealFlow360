import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "@/lib/api"
import type {
  FulfillmentDetail,
  FulfillmentStatus,
  OverrideRowInput,
  Page,
  FulfillmentRow,
  StockItem,
} from "@/types/api"

export const fulfillmentKeys = {
  list: (params: unknown) => ["fulfillments", "list", params] as const,
  detail: (id: string) => ["fulfillment", id] as const,
  stock: () => ["fulfillments", "stock"] as const,
}

export function useFulfillmentList(params: {
  page: number
  size: number
  status?: FulfillmentStatus | "all"
  openOnly?: boolean
}) {
  return useQuery({
    queryKey: fulfillmentKeys.list(params),
    queryFn: async () => {
      const search = new URLSearchParams({
        page: String(params.page),
        size: String(params.size),
      })
      if (params.status && params.status !== "all") search.set("status", params.status)
      if (params.openOnly) search.set("open_only", "true")
      const { data } = await api.get<Page<FulfillmentRow>>(`/fulfillments?${search}`)
      return data
    },
    staleTime: 10_000,
  })
}

/** The live per-warehouse stock table at the top of screen 7. */
export function useStock() {
  return useQuery({
    queryKey: fulfillmentKeys.stock(),
    queryFn: async () => (await api.get<StockItem[]>("/admin/stock")).data,
    staleTime: 15_000,
  })
}

export function useFulfillment(id: string | undefined) {
  return useQuery({
    queryKey: fulfillmentKeys.detail(id ?? ""),
    queryFn: async () =>
      (await api.get<FulfillmentDetail>(`/fulfillments/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useFulfillmentActions(id: string | undefined) {
  const queryClient = useQueryClient()

  const apply = (updated: FulfillmentDetail) => {
    queryClient.setQueryData(fulfillmentKeys.detail(updated.id), updated)
    queryClient.invalidateQueries({ queryKey: ["fulfillments"] })
    // Reservations and dispatches both move stock.
    queryClient.invalidateQueries({ queryKey: fulfillmentKeys.stock() })
    queryClient.invalidateQueries({ queryKey: ["quotations"] })
  }

  const fail = (fallback: string) => (caught: unknown) =>
    toast.error(errorMessage(caught, fallback))

  const accept = useMutation({
    mutationFn: async () =>
      (await api.post<FulfillmentDetail>(`/fulfillments/${id}/accept`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Split accepted — stock reserved and shipments planned.")
    },
    onError: fail("Could not accept the split."),
  })

  const override = useMutation({
    mutationFn: async (rows: OverrideRowInput[]) =>
      (await api.post<FulfillmentDetail>(`/fulfillments/${id}/override`, { rows }))
        .data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Split overridden.")
    },
    onError: fail("Could not override the split."),
  })

  const consolidate = useMutation({
    mutationFn: async () =>
      (await api.post<FulfillmentDetail>(`/fulfillments/${id}/consolidate`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Backorder consolidated into the existing shipment.")
    },
    onError: fail("Could not consolidate the backorder."),
  })

  const ship = useMutation({
    mutationFn: async (shipmentId: string) =>
      (await api.post<FulfillmentDetail>(`/shipments/${shipmentId}/ship`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Shipped. Those units are now billable.")
    },
    onError: fail("Could not ship."),
  })

  return { accept, override, consolidate, ship }
}

/** Confirming a quotation is what creates its fulfillment in the first place. */
export function useConfirmQuotation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (quotationId: string) =>
      (await api.post<FulfillmentDetail>(`/quotations/${quotationId}/confirm`)).data,
    onSuccess: (fulfillment) => {
      queryClient.invalidateQueries({ queryKey: ["quotations"] })
      queryClient.invalidateQueries({
        queryKey: ["quotation", fulfillment.quotation_id],
      })
      queryClient.invalidateQueries({ queryKey: ["fulfillments"] })
      toast.success("Order confirmed — a warehouse split has been suggested.")
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not confirm the order.")),
  })
}
