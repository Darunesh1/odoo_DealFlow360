import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeftIcon, CheckIcon, MessageSquareIcon, SendIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { money, statusTone } from "@/features/quotations/format"
import { useMyQuotation, usePortalActions } from "@/features/portal/use-portal"
import { QUOTATION_STAGE_LABELS } from "@/types/api"

export default function PortalQuotationDetailPage() {
  const { quotationId } = useParams<{ quotationId: string }>()
  const { data: quotation, isLoading } = useMyQuotation(quotationId)
  const actions = usePortalActions(quotationId)

  const [commentLine, setCommentLine] = useState<string | null>(null)
  const [comment, setComment] = useState("")
  const [counter, setCounter] = useState("")
  const [wantedDate, setWantedDate] = useState("")
  const [note, setNote] = useState("")

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>
  if (!quotation) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          We could not find that quotation.
        </CardContent>
      </Card>
    )
  }

  const openRequest = quotation.change_requests.find(
    (request) => request.status === "open"
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/portal"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> My quotations
          </Link>
        }
        title={quotation.number}
        description="Ask about a line, propose different terms, or confirm the quotation as it stands."
      />

      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={statusTone(quotation.status)}>
          {QUOTATION_STAGE_LABELS[quotation.status]}
        </Badge>
        <span className="font-mono text-xl tabular-nums">
          {money(quotation.total, quotation.currency)}
        </span>
        {quotation.valid_until ? (
          <span className="text-sm text-muted-foreground">
            valid until {new Date(quotation.valid_until).toLocaleDateString()}
          </span>
        ) : null}
      </div>

      {openRequest ? (
        <Card className="border-amber-500/40 bg-amber-500/[0.04]">
          <CardContent className="py-4">
            <p className="text-sm font-medium">Your request is with us</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {openRequest.counter_discount_percent !== null
                ? `You asked for ${openRequest.counter_discount_percent}% off. `
                : ""}
              {openRequest.note ?? ""} We will come back to you shortly.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">What is included</CardTitle>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Discount</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {quotation.lines.map((line) => (
                  <TableRow key={line.id}>
                    <TableCell>
                      <p className="font-medium leading-tight">{line.product_name}</p>
                      {line.variant_name ? (
                        <p className="text-xs text-muted-foreground">
                          {line.variant_name}
                        </p>
                      ) : null}
                      {line.is_recurring ? (
                        <Badge variant="outline" className="mt-1 capitalize">
                          {line.recurring_interval}
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {line.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {money(line.unit_price, quotation.currency)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                      {line.discount_percent}%
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {money(line.line_total, quotation.currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7"
                        onClick={() =>
                          setCommentLine(commentLine === line.id ? null : line.id)
                        }
                      >
                        <MessageSquareIcon className="size-3.5" />
                        <span className="sr-only">Ask about this line</span>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <dl className="space-y-1.5 border-t px-6 pt-4 text-sm">
            <Row label="Subtotal">{money(quotation.subtotal, quotation.currency)}</Row>
            <Row label="Discount">
              − {money(quotation.discount_total, quotation.currency)}
            </Row>
            <Row label="Tax">{money(quotation.tax_total, quotation.currency)}</Row>
            <Row label="Total">
              <span className="font-medium">
                {money(quotation.total, quotation.currency)}
              </span>
            </Row>
          </dl>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Questions and comments</CardTitle>
            <CardDescription>
              {commentLine
                ? "Your comment will be attached to the line you picked."
                : "Pick a line above to ask about it, or write a general note."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {quotation.comments.length > 0 ? (
              <div className="space-y-2">
                {quotation.comments.map((entry) => (
                  <div key={entry.id} className="rounded-lg border p-3 text-sm">
                    <p className="font-medium">{entry.author_name}</p>
                    <p className="mt-0.5 text-muted-foreground">{entry.body}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {new Date(entry.created_at).toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            <Textarea
              rows={3}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Can this be delivered next month?"
            />
            <Button
              className="w-full"
              disabled={!comment.trim() || actions.comment.isPending}
              onClick={() =>
                actions.comment.mutate(
                  {
                    body: comment,
                    quotation_line_id: commentLine ?? undefined,
                  },
                  {
                    onSuccess: () => {
                      setComment("")
                      setCommentLine(null)
                    },
                  }
                )
              }
            >
              <SendIcon /> Send
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Propose different terms</CardTitle>
            <CardDescription>
              Ask for a different discount or delivery date. Nothing changes
              until your account manager accepts.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label>Counter discount %</Label>
              <Input
                type="number"
                min={0}
                max={100}
                step="0.5"
                value={counter}
                onChange={(event) => setCounter(event.target.value)}
                disabled={!quotation.can_negotiate}
                className="font-mono tabular-nums"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Requested delivery date</Label>
              <Input
                type="date"
                value={wantedDate}
                onChange={(event) => setWantedDate(event.target.value)}
                disabled={!quotation.can_negotiate}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Anything else</Label>
              <Textarea
                rows={2}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                disabled={!quotation.can_negotiate}
                placeholder="We are planning a larger order next quarter."
              />
            </div>

            <Button
              variant="outline"
              className="w-full"
              disabled={
                !quotation.can_negotiate ||
                actions.requestChanges.isPending ||
                (!counter && !wantedDate && !note.trim())
              }
              onClick={() =>
                actions.requestChanges.mutate(
                  {
                    counter_discount_percent: counter ? Number(counter) : undefined,
                    requested_delivery_date: wantedDate || undefined,
                    note: note.trim() || undefined,
                  },
                  {
                    onSuccess: () => {
                      setCounter("")
                      setWantedDate("")
                      setNote("")
                    },
                  }
                )
              }
            >
              Submit request
            </Button>

            <Button
              className="w-full"
              disabled={!quotation.can_confirm || actions.confirm.isPending}
              onClick={() => actions.confirm.mutate()}
            >
              <CheckIcon /> Confirm quotation
            </Button>
            {!quotation.can_confirm && quotation.status !== "confirmed" ? (
              <p className="text-xs text-muted-foreground">
                {openRequest
                  ? "You can confirm once we have answered your request."
                  : "This quotation is not ready to confirm yet."}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono tabular-nums">{children}</dd>
    </div>
  )
}
