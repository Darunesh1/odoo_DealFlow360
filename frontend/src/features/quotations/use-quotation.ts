import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "@/lib/api"
import type {
  Currency,
  Customer,
  PickerProduct,
  Quotation,
  QuotationCreateInput,
  QuotationLineCreateInput,
  QuotationLineUpdateInput,
  QuotationListPage,
  QuotationListRow,
  QuotationSort,
  QuotationStatus,
  QuotationSubmitResponse,
  QuotationUpdateInput,
  UpsellSuggestion,
} from "@/types/api"

/**
 * One place for every quotation query key, so a mutation cannot invalidate a
 * key that no longer matches the one a component reads.
 */
export const quotationKeys = {
  list: (params: unknown) => ["quotations", "list", params] as const,
  pipeline: () => ["quotations", "pipeline"] as const,
  detail: (id: string) => ["quotation", id] as const,
  suggestions: (id: string) => ["quotation", id, "suggestions"] as const,
}

export interface QuotationListParams {
  page: number
  size: number
  search?: string
  status?: QuotationStatus | "all"
  sort?: QuotationSort
  order?: "asc" | "desc"
}

export function useQuotationList(params: QuotationListParams) {
  return useQuery({
    queryKey: quotationKeys.list(params),
    queryFn: async () => {
      const search = new URLSearchParams({
        page: String(params.page),
        size: String(params.size),
        sort: params.sort ?? "updated",
        order: params.order ?? "desc",
      })
      if (params.search) search.set("search", params.search)
      if (params.status && params.status !== "all") search.set("status", params.status)
      const { data } = await api.get<QuotationListPage>(`/quotations?${search}`)
      return data
    },
    // The stage counts and totals move as colleagues work; a stale board is
    // worse than a brief spinner.
    staleTime: 10_000,
  })
}

export function usePipeline() {
  return useQuery({
    queryKey: quotationKeys.pipeline(),
    queryFn: async () => {
      const { data } = await api.get<Record<QuotationStatus, QuotationListRow[]>>(
        "/quotations/pipeline"
      )
      return data
    },
    staleTime: 10_000,
  })
}

export function useQuotation(id: string | undefined) {
  return useQuery({
    queryKey: quotationKeys.detail(id ?? ""),
    queryFn: async () => (await api.get<Quotation>(`/quotations/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useSuggestions(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: quotationKeys.suggestions(id ?? ""),
    queryFn: async () =>
      (await api.get<UpsellSuggestion[]>(`/quotations/${id}/suggestions`)).data,
    enabled: Boolean(id) && enabled,
  })
}

/** The three pickers every quotation screen needs. Cached hard: an admin edits
 *  the catalog far less often than a rep reads it. */
export function useQuotationLookups() {
  const customers = useQuery({
    queryKey: ["lookups", "customers"],
    queryFn: async () => (await api.get<Customer[]>("/lookups/customers")).data,
    staleTime: 300_000,
  })
  const products = useQuery({
    queryKey: ["lookups", "products"],
    queryFn: async () => (await api.get<PickerProduct[]>("/lookups/products")).data,
    staleTime: 300_000,
  })
  const currencies = useQuery({
    queryKey: ["lookups", "currencies"],
    queryFn: async () => (await api.get<Currency[]>("/lookups/currencies")).data,
    staleTime: 300_000,
  })
  return { customers, products, currencies }
}

/**
 * Every write goes through here.
 *
 * The API answers each mutation with the whole recalculated quotation, so the
 * detail cache is *set* from the response rather than refetched - that is what
 * makes the Limit and Status columns move the instant a discount changes,
 * without a second round trip.
 */
export function useQuotationMutations(id: string | undefined) {
  const queryClient = useQueryClient()

  const applyQuotation = (updated: Quotation) => {
    queryClient.setQueryData(quotationKeys.detail(updated.id), updated)
    queryClient.invalidateQueries({ queryKey: ["quotations"] })
    // A changed line set changes what is worth suggesting.
    queryClient.invalidateQueries({ queryKey: quotationKeys.suggestions(updated.id) })
  }

  const fail = (fallback: string) => (caught: unknown) =>
    toast.error(errorMessage(caught, fallback))

  const create = useMutation({
    mutationFn: async (body: QuotationCreateInput) =>
      (await api.post<Quotation>("/quotations", body)).data,
    onSuccess: applyQuotation,
    onError: fail("Could not create the quotation."),
  })

  const update = useMutation({
    mutationFn: async (body: QuotationUpdateInput) =>
      (await api.patch<Quotation>(`/quotations/${id}`, body)).data,
    onSuccess: applyQuotation,
    onError: fail("Could not save the quotation."),
  })

  const setOrderDiscount = useMutation({
    mutationFn: async (order_discount_percent: number) =>
      (
        await api.patch<Quotation>(`/quotations/${id}/discount`, {
          order_discount_percent,
        })
      ).data,
    onSuccess: applyQuotation,
    onError: fail("Could not apply the order discount."),
  })

  const addLine = useMutation({
    mutationFn: async (body: QuotationLineCreateInput) =>
      (await api.post<Quotation>(`/quotations/${id}/lines`, body)).data,
    onSuccess: applyQuotation,
    onError: fail("Could not add the line."),
  })

  const updateLine = useMutation({
    mutationFn: async ({
      lineId,
      body,
    }: {
      lineId: string
      body: QuotationLineUpdateInput
    }) => (await api.patch<Quotation>(`/quotations/${id}/lines/${lineId}`, body)).data,
    onSuccess: applyQuotation,
    onError: fail("Could not update the line."),
  })

  const removeLine = useMutation({
    mutationFn: async (lineId: string) =>
      (await api.delete<Quotation>(`/quotations/${id}/lines/${lineId}`)).data,
    onSuccess: applyQuotation,
    onError: fail("Could not remove the line."),
  })

  const reload = useMutation({
    mutationFn: async () =>
      (await api.post<Quotation>(`/quotations/${id}/reload`)).data,
    onSuccess: (updated) => {
      applyQuotation(updated)
      toast.success("Prices, stock and limits refreshed from the catalog.")
    },
    onError: fail("Could not refresh from the catalog."),
  })

  const submit = useMutation({
    mutationFn: async () =>
      (await api.post<QuotationSubmitResponse>(`/quotations/${id}/submit`)).data,
    onSuccess: (result) => {
      applyQuotation(result.quotation)
      toast.success(
        result.approval_required
          ? `Submitted for approval — ${result.approval?.rule_name ?? "routed"}.`
          : "Within every limit, so it was approved automatically."
      )
    },
    onError: fail("Could not submit for approval."),
  })

  const dismissSuggestion = useMutation({
    mutationFn: async (productId: string) => {
      await api.post(`/quotations/${id}/suggestions/${productId}/dismiss`)
      return productId
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: quotationKeys.suggestions(id ?? "") })
    },
    onError: fail("Could not dismiss the suggestion."),
  })

  const remove = useMutation({
    mutationFn: async (quotationId: string) => {
      await api.delete(`/quotations/${quotationId}`)
      return quotationId
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotations"] })
      toast.success("Draft deleted.")
    },
    onError: fail("Could not delete the quotation."),
  })

  return {
    create,
    update,
    setOrderDiscount,
    addLine,
    updateLine,
    removeLine,
    reload,
    submit,
    dismissSuggestion,
    remove,
  }
}

/** Emails the customer their portal link, creating their login if needed. */
export function useSendToCustomer(id: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (recipientEmail?: string) =>
      (
        await api.post<Quotation>(`/quotations/${id}/send`, {
          recipient_email: recipientEmail ?? null,
        })
      ).data,
    onSuccess: (updated) => {
      queryClient.setQueryData(quotationKeys.detail(updated.id), updated)
      toast.success(
        `Sent to ${updated.recipient_email ?? "the customer"} — they can review and negotiate in their portal.`
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not send the quotation.")),
  })
}
