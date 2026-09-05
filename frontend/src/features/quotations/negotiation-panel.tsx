import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckIcon, SendIcon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { api, errorMessage } from "@/lib/api"
import type { Negotiation } from "@/types/api"

/**
 * The rep's side of the portal conversation (spec B8).
 *
 * Accepting a counter re-runs the discount governance, so the button says so:
 * a rep clicking Accept needs to know it may send the deal back for approval.
 */
export function NegotiationPanel({ quotationId }: { quotationId: string }) {
  const queryClient = useQueryClient()
  const [reply, setReply] = useState("")

  const { data } = useQuery({
    queryKey: ["quotation", quotationId, "negotiation"],
    queryFn: async () =>
      (await api.get<Negotiation>(`/quotations/${quotationId}/negotiation`)).data,
  })

  const refresh = () => {
    queryClient.invalidateQueries({
      queryKey: ["quotation", quotationId, "negotiation"],
    })
    queryClient.invalidateQueries({ queryKey: ["quotation", quotationId] })
    queryClient.invalidateQueries({ queryKey: ["quotations"] })
  }

  const comment = useMutation({
    mutationFn: async (body: string) =>
      (await api.post(`/quotations/${quotationId}/comments`, { body })).data,
    onSuccess: () => {
      refresh()
      setReply("")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not reply.")),
  })

  const accept = useMutation({
    mutationFn: async (requestId: string) =>
      (
        await api.post(
          `/quotations/${quotationId}/change-requests/${requestId}/accept`
        )
      ).data as { approval_required: boolean },
    onSuccess: (result) => {
      refresh()
      toast.success(
        result.approval_required
          ? "Accepted — the new terms need approval again."
          : "Accepted — within every limit, so it is approved."
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not accept that request.")),
  })

  const reject = useMutation({
    mutationFn: async (requestId: string) =>
      (
        await api.post(
          `/quotations/${quotationId}/change-requests/${requestId}/reject`,
          { note: reply.trim() || undefined }
        )
      ).data,
    onSuccess: () => {
      refresh()
      setReply("")
      toast.success("Declined. The customer keeps the terms they were sent.")
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not decline that request.")),
  })

  const open = (data?.change_requests ?? []).filter(
    (request) => request.status === "open"
  )
  const hasHistory =
    (data?.comments.length ?? 0) > 0 || (data?.change_requests.length ?? 0) > 0

  if (!hasHistory) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Customer negotiation</CardTitle>
        <CardDescription>
          Accepting a counter re-runs the discount governance on the new terms.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {open.map((request) => (
          <div
            key={request.id}
            className="space-y-3 rounded-lg border border-amber-500/40 bg-amber-500/[0.04] p-3"
          >
            <div>
              <p className="text-sm font-medium">
                {request.requested_by_name} asked for
                {request.counter_discount_percent !== null
                  ? ` ${request.counter_discount_percent}% off`
                  : " a change"}
              </p>
              {request.requested_delivery_date ? (
                <p className="text-sm text-muted-foreground">
                  Delivery by{" "}
                  {new Date(request.requested_delivery_date).toLocaleDateString()}
                </p>
              ) : null}
              {request.note ? (
                <p className="mt-1 text-sm text-muted-foreground">
                  “{request.note}”
                </p>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => accept.mutate(request.id)}
                disabled={accept.isPending}
              >
                <CheckIcon /> Accept and re-check
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => reject.mutate(request.id)}
                disabled={reject.isPending}
              >
                <XIcon /> Decline
              </Button>
            </div>
          </div>
        ))}

        {(data?.comments ?? []).map((entry) => (
          <div key={entry.id} className="rounded-lg border p-3 text-sm">
            <div className="flex items-center gap-2">
              <p className="font-medium">{entry.author_name}</p>
              {entry.is_internal ? (
                <Badge variant="outline">Internal</Badge>
              ) : null}
            </div>
            <p className="mt-0.5 text-muted-foreground">{entry.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {new Date(entry.created_at).toLocaleString()}
            </p>
          </div>
        ))}

        <div className="space-y-2">
          <Textarea
            rows={2}
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            placeholder="Reply to the customer…"
          />
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={!reply.trim() || comment.isPending}
            onClick={() => comment.mutate(reply)}
          >
            <SendIcon /> Send reply
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
