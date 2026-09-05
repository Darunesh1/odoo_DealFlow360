import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, errorMessage } from "@/lib/api"
import type {
  ApprovalDecision,
  ApprovalDetail,
  ApprovalListPage,
  ApprovalStatus,
} from "@/types/api"

export const approvalKeys = {
  list: (params: unknown) => ["approvals", "list", params] as const,
  detail: (id: string) => ["approval", id] as const,
}

export interface ApprovalListParams {
  page: number
  size: number
  status?: ApprovalStatus | "all"
  mine?: boolean
  search?: string
}

export function useApprovalList(params: ApprovalListParams) {
  return useQuery({
    queryKey: approvalKeys.list(params),
    queryFn: async () => {
      const search = new URLSearchParams({
        page: String(params.page),
        size: String(params.size),
      })
      if (params.status && params.status !== "all") search.set("status", params.status)
      if (params.mine) search.set("mine", "true")
      if (params.search) search.set("search", params.search)
      const { data } = await api.get<ApprovalListPage>(`/approvals?${search}`)
      return data
    },
    staleTime: 10_000,
  })
}

export function useApproval(id: string | undefined) {
  return useQuery({
    queryKey: approvalKeys.detail(id ?? ""),
    queryFn: async () => (await api.get<ApprovalDetail>(`/approvals/${id}`)).data,
    enabled: Boolean(id),
  })
}

export function useApprovalDecision(id: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: { decision: ApprovalDecision; note?: string }) =>
      (await api.post<ApprovalDetail>(`/approvals/${id}/decision`, body)).data,
    onSuccess: (updated) => {
      queryClient.setQueryData(approvalKeys.detail(updated.id), updated)
      queryClient.invalidateQueries({ queryKey: ["approvals"] })
      // The decision moved the quotation's status too.
      queryClient.invalidateQueries({ queryKey: ["quotations"] })
      queryClient.invalidateQueries({
        queryKey: ["quotation", updated.quotation_id],
      })
      toast.success(
        updated.status === "pending"
          ? "Approved — it now sits with the next approver."
          : `Quotation ${updated.status.replace("_", " ")}.`
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not record that decision.")),
  })
}
