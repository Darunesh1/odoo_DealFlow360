import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "@/lib/api"
import type {
  CreditNote,
  CreditNoteCounts,
  Invoice,
  InvoiceCounts,
  InvoiceDetail,
  InvoiceStatus,
  Page,
  PaymentMethod,
  Subscription,
  SubscriptionCounts,
  SubscriptionDetail,
  SubscriptionStatus,
} from "@/types/api"

export const billingKeys = {
  subscriptions: (params: unknown) => ["subscriptions", params] as const,
  subscriptionCounts: () => ["subscriptions", "counts"] as const,
  subscription: (id: string) => ["subscription", id] as const,
  invoices: (params: unknown) => ["invoices", params] as const,
  invoiceCounts: () => ["invoices", "counts"] as const,
  invoice: (id: string) => ["invoice", id] as const,
}

export function useSubscriptions(params: {
  page: number
  size: number
  status?: SubscriptionStatus | "all"
}) {
  return useQuery({
    queryKey: billingKeys.subscriptions(params),
    queryFn: async () => {
      const search = new URLSearchParams({
        page: String(params.page),
        size: String(params.size),
      })
      if (params.status && params.status !== "all") search.set("status", params.status)
      const { data } = await api.get<Page<Subscription>>(`/subscriptions?${search}`)
      return data
    },
    staleTime: 15_000,
  })
}

export function useSubscriptionCounts() {
  return useQuery({
    queryKey: billingKeys.subscriptionCounts(),
    queryFn: async () =>
      (await api.get<SubscriptionCounts>("/subscriptions/counts")).data,
    staleTime: 15_000,
  })
}

export function useSubscription(id: string | undefined) {
  return useQuery({
    queryKey: billingKeys.subscription(id ?? ""),
    queryFn: async () =>
      (await api.get<SubscriptionDetail>(`/subscriptions/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useSubscriptionActions(id: string | undefined) {
  const queryClient = useQueryClient()

  const apply = (updated: SubscriptionDetail) => {
    queryClient.setQueryData(billingKeys.subscription(updated.id), updated)
    queryClient.invalidateQueries({ queryKey: ["subscriptions"] })
    // A proration lands on the next invoice, so the invoice list moves too.
    queryClient.invalidateQueries({ queryKey: ["invoices"] })
  }

  const fail = (fallback: string) => (caught: unknown) =>
    toast.error(errorMessage(caught, fallback))

  const changeQuantity = useMutation({
    mutationFn: async (body: {
      quantity: number
      effective_date?: string
      reason?: string
    }) =>
      (await api.post<SubscriptionDetail>(`/subscriptions/${id}/quantity`, body)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Quantity changed — the remainder of this period is prorated.")
    },
    onError: fail("Could not change the quantity."),
  })

  const pause = useMutation({
    mutationFn: async () =>
      (await api.post<SubscriptionDetail>(`/subscriptions/${id}/pause`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Paused. Billing stops until it is resumed.")
    },
    onError: fail("Could not pause the subscription."),
  })

  const resume = useMutation({
    mutationFn: async () =>
      (await api.post<SubscriptionDetail>(`/subscriptions/${id}/resume`)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success("Resumed.")
    },
    onError: fail("Could not resume the subscription."),
  })

  const cancel = useMutation({
    mutationFn: async (body: { at_period_end: boolean; reason?: string }) =>
      (await api.post<SubscriptionDetail>(`/subscriptions/${id}/cancel`, body)).data,
    onSuccess: (updated) => {
      apply(updated)
      toast.success(
        updated.cancel_at_period_end
          ? "Will end when the current period runs out."
          : "Cancelled — the unused remainder has been credited."
      )
    },
    onError: fail("Could not cancel the subscription."),
  })

  return { changeQuantity, pause, resume, cancel }
}

export function useInvoices(params: {
  page: number
  size: number
  status?: InvoiceStatus | "all"
}) {
  return useQuery({
    queryKey: billingKeys.invoices(params),
    queryFn: async () => {
      const search = new URLSearchParams({
        page: String(params.page),
        size: String(params.size),
      })
      if (params.status && params.status !== "all") search.set("status", params.status)
      const { data } = await api.get<Page<Invoice>>(`/invoices?${search}`)
      return data
    },
    staleTime: 15_000,
  })
}

export function useInvoiceCounts() {
  return useQuery({
    queryKey: billingKeys.invoiceCounts(),
    queryFn: async () => (await api.get<InvoiceCounts>("/invoices/counts")).data,
    staleTime: 15_000,
  })
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: billingKeys.invoice(id ?? ""),
    queryFn: async () => (await api.get<InvoiceDetail>(`/invoices/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useRecordPayment(id: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      amount: number
      method: PaymentMethod
      reference?: string
      received_on?: string
      note?: string
    }) => (await api.post<InvoiceDetail>(`/invoices/${id}/payments`, body)).data,
    onSuccess: (updated) => {
      queryClient.setQueryData(billingKeys.invoice(updated.id), updated)
      queryClient.invalidateQueries({ queryKey: ["invoices"] })
      toast.success(
        updated.status === "paid"
          ? "Paid in full."
          : "Payment recorded — part of the balance is still outstanding."
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not record that payment.")),
  })
}

/** Bills whatever has shipped and is not yet on an invoice. */
export function useInvoiceOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (quotationId: string) =>
      (await api.post<InvoiceDetail | null>(`/quotations/${quotationId}/invoice`)).data,
    onSuccess: (invoice) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] })
      toast.success(
        invoice
          ? `Invoice ${invoice.number} raised for what has shipped.`
          : "Nothing new has shipped, so there is nothing to bill yet."
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not raise the invoice.")),
  })
}

export function useCreditNotes() {
  return useQuery({
    queryKey: ["credit-notes"],
    queryFn: async () => (await api.get<CreditNote[]>("/credit-notes")).data,
    staleTime: 15_000,
  })
}

export function useCreditNoteCounts() {
  return useQuery({
    queryKey: ["credit-notes", "counts"],
    queryFn: async () =>
      (await api.get<CreditNoteCounts>("/credit-notes/counts")).data,
    staleTime: 15_000,
  })
}

/** Settles part of an invoice with credit the customer is already owed. */
export function useApplyCreditNote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      noteId,
      invoiceId,
    }: {
      noteId: string
      invoiceId: string
    }) =>
      (
        await api.post<CreditNote>(`/credit-notes/${noteId}/apply`, {
          invoice_id: invoiceId,
        })
      ).data,
    onSuccess: (note) => {
      queryClient.invalidateQueries({ queryKey: ["credit-notes"] })
      // The invoice's balance moved too.
      queryClient.invalidateQueries({ queryKey: ["invoices"] })
      if (note.invoice_id) {
        queryClient.invalidateQueries({ queryKey: ["invoice", note.invoice_id] })
      }
      toast.success(`${note.number} applied to ${note.invoice_number}.`)
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not apply that credit note.")),
  })
}
