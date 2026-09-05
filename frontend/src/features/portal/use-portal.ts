import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "@/lib/api"
import type {
  PortalInvoiceRow,
  PortalQuotation,
  PortalQuotationRow,
} from "@/types/api"

export const portalKeys = {
  quotations: () => ["portal", "quotations"] as const,
  quotation: (id: string) => ["portal", "quotation", id] as const,
  invoices: () => ["portal", "invoices"] as const,
}

export function useMyQuotations() {
  return useQuery({
    queryKey: portalKeys.quotations(),
    queryFn: async () =>
      (await api.get<PortalQuotationRow[]>("/portal/quotations")).data,
  })
}

export function useMyQuotation(id: string | undefined) {
  return useQuery({
    queryKey: portalKeys.quotation(id ?? ""),
    queryFn: async () =>
      (await api.get<PortalQuotation>(`/portal/quotations/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useMyInvoices() {
  return useQuery({
    queryKey: portalKeys.invoices(),
    queryFn: async () =>
      (await api.get<PortalInvoiceRow[]>("/portal/invoices")).data,
  })
}

export function usePortalActions(id: string | undefined) {
  const queryClient = useQueryClient()

  const apply = (updated: PortalQuotation) => {
    queryClient.setQueryData(portalKeys.quotation(updated.id), updated)
    queryClient.invalidateQueries({ queryKey: portalKeys.quotations() })
  }

  const fail = (fallback: string) => (caught: unknown) =>
    toast.error(errorMessage(caught, fallback))

  const comment = useMutation({
    mutationFn: async (body: { body: string; quotation_line_id?: string }) =>
      (await api.post<PortalQuotation>(`/portal/quotations/${id}/comments`, body))
        .data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Sent. Your account manager will see it.")
    },
    onError: fail("Could not send that comment."),
  })

  const requestChanges = useMutation({
    mutationFn: async (body: {
      counter_discount_percent?: number
      requested_delivery_date?: string
      note?: string
    }) =>
      (
        await api.post<PortalQuotation>(
          `/portal/quotations/${id}/change-requests`,
          body
        )
      ).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Request sent. We will come back to you shortly.")
    },
    onError: fail("Could not send that request."),
  })

  const confirm = useMutation({
    mutationFn: async () =>
      (await api.post<PortalQuotation>(`/portal/quotations/${id}/confirm`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Confirmed. Your order is being prepared.")
    },
    onError: fail("Could not confirm the quotation."),
  })

  return { comment, requestChanges, confirm }
}
