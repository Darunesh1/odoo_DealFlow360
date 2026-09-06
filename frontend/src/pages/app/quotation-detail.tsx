import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  MailIcon,
  RefreshCwIcon,
  SendIcon,
  TruckIcon,
} from "lucide-react"

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
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { LineRow } from "@/features/quotations/line-row"
import { NegotiationPanel } from "@/features/quotations/negotiation-panel"
import { statusTone } from "@/features/quotations/format"
import { ProductPicker } from "@/features/quotations/product-picker"
import { RiskBadge } from "@/features/quotations/risk-badge"
import { TotalsBar } from "@/features/quotations/totals-bar"
import { UpsellPanel } from "@/features/quotations/upsell-panel"
import {
  useQuotation,
  useQuotationLookups,
  useQuotationMutations,
  useSuggestions,
} from "@/features/quotations/use-quotation"
import { useConfirmQuotation } from "@/features/fulfillment/use-fulfillment"
import { useSendToCustomer } from "@/features/quotations/use-quotation"
import { QUOTATION_STAGE_LABELS } from "@/types/api"

export default function QuotationDetailPage() {
  const { quotationId } = useParams<{ quotationId: string }>()
  const { data: quotation, isLoading } = useQuotation(quotationId)
  const { products } = useQuotationLookups()
  const mutations = useQuotationMutations(quotationId)
  const confirm = useConfirmQuotation()
  const navigate = useNavigate()
  const sendToCustomer = useSendToCustomer(quotationId)

  // A submitted quotation is read-only: nearly every column on a line is a
  // snapshot precisely so an approver sees what the rep sent, not what the
  // rep has since changed.
  const editable = quotation?.status === "draft"

  const { data: suggestions, isLoading: loadingSuggestions } = useSuggestions(
    quotationId,
    Boolean(editable)
  )

  const [notes, setNotes] = useState<string | null>(null)
  const [orderDiscount, setOrderDiscount] = useState<string | null>(null)

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading quotation…</p>
  }
  if (!quotation) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          That quotation does not exist, or is not yours to see.
        </CardContent>
      </Card>
    )
  }

  const overLines = quotation.lines.filter((line) => line.over_by_points > 0)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/app/quotations"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> Quotations
          </Link>
        }
        title={`${quotation.number} · ${quotation.customer.name}`}
        description="Add products, apply discounts, and review upsell suggestions. Each line is checked against its own limit as you type."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {editable ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => mutations.reload.mutate()}
                disabled={mutations.reload.isPending}
              >
                <RefreshCwIcon /> Reload data
              </Button>
            ) : null}
            {editable ? (
              <Button
                size="sm"
                onClick={() => mutations.submit.mutate()}
                disabled={
                  mutations.submit.isPending || quotation.lines.length === 0
                }
              >
                <SendIcon /> Submit for approval
              </Button>
            ) : null}
            {/* Approved is the only state a confirmation is legal from: it is
                what reserves stock and opens the subscriptions. */}
            {quotation.status === "approved" ? (
              <Button
                size="sm"
                onClick={() =>
                  confirm.mutate(quotation.id, {
                    onSuccess: (fulfillment) =>
                      navigate(`/app/fulfillment/${fulfillment.id}`),
                  })
                }
                disabled={confirm.isPending}
              >
                <CheckCircle2Icon /> Confirm order
              </Button>
            ) : null}
            {quotation.status === "approved" || quotation.status === "negotiation" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => sendToCustomer.mutate(undefined)}
                disabled={sendToCustomer.isPending}
              >
                <MailIcon /> Send to customer
              </Button>
            ) : null}
            {quotation.status === "confirmed" ? (
              <Button variant="outline" size="sm" asChild>
                <Link to="/app/fulfillment">
                  <TruckIcon /> Fulfillment
                </Link>
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={statusTone(quotation.status)}>
          {QUOTATION_STAGE_LABELS[quotation.status]}
        </Badge>
        <RiskBadge band={quotation.risk_band} score={quotation.blended_risk_score} />
        {quotation.customer_tier ? (
          <span className="text-sm text-muted-foreground">
            {quotation.customer_tier.name} tier · up to{" "}
            {quotation.customer_tier.max_discount_percent}%
          </span>
        ) : null}
        <span className="text-sm text-muted-foreground">· {quotation.currency}</span>
      </div>

      <TotalsBar quotation={quotation} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          {editable ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Add a line</CardTitle>
                <CardDescription>
                  Products across every category. Prices resolve for{" "}
                  {quotation.customer.name}&apos;s tier in {quotation.currency}.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ProductPicker
                  products={products.data ?? []}
                  disabled={mutations.addLine.isPending || mutations.updateLine.isPending}
                  onAdd={({ variantId, quantity, discount }) =>
                    mutations.addLine.mutate({
                      variant_id: variantId,
                      quantity,
                      line_discount_percent: discount,
                      source: "manual",
                    })
                  }
                />
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Order lines</CardTitle>
              <CardDescription>
                Each line is measured against the stricter of its customer tier
                and its category ceiling.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              {quotation.lines.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-muted-foreground">
                  No lines yet. Add a product above.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Product</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead className="text-right">Price</TableHead>
                        <TableHead>Discount</TableHead>
                        <TableHead className="text-right">Limit</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">
                          Amount
                          {quotation.tax_total > 0 ? (
                            <span className="ml-1 font-normal text-muted-foreground">
                              (ex. tax)
                            </span>
                          ) : null}
                        </TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {quotation.lines.map((line) => (
                        <LineRow
                          key={line.id}
                          line={line}
                          currency={quotation.currency}
                          editable={Boolean(editable)}
                          orderDiscount={quotation.order_discount_percent}
                          onChange={(body) =>
                            mutations.updateLine.mutate({ lineId: line.id, body })
                          }
                          onRemove={() => mutations.removeLine.mutate(line.id)}
                        />
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {overLines.length > 0 ? (
            <Card className="border-amber-500/40 bg-amber-500/[0.04]">
              <CardHeader>
                <CardTitle className="text-base">
                  {overLines.length === 1
                    ? "One line is over its limit"
                    : `${overLines.length} lines are over their limits`}
                </CardTitle>
                <CardDescription>
                  Submitting will route this quotation for approval automatically.
                  The blended score is {quotation.blended_risk_score.toFixed(2)}.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {overLines.map((line) => (
                  <p key={line.id} className="text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {line.product_name}
                    </span>{" "}
                    — {line.discount_percent}% given, {line.allowed_discount_percent}%
                    allowed,{" "}
                    <span className="font-medium text-red-600 dark:text-red-400">
                      {line.over_by_points} pt over
                    </span>
                  </p>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          {editable ? (
            <UpsellPanel
              suggestions={suggestions ?? []}
              currency={quotation.currency}
              isLoading={loadingSuggestions}
              disabled={mutations.addLine.isPending}
              onAdd={(suggestion) =>
                mutations.addLine.mutate({
                  variant_id: suggestion.variant_id,
                  quantity: 1,
                  line_discount_percent: 0,
                  source: "upsell",
                })
              }
              onDismiss={(suggestion) =>
                mutations.dismissSuggestion.mutate(suggestion.product_id)
              }
              onUpgrade={(suggestion) => {
                // Swap the line rather than adding one: the same PATCH the
                // quantity field uses, so re-pricing, the capacity check and
                // the risk recalculation all happen on the path that already
                // exists.
                if (!suggestion.replaces_line_id) return
                mutations.updateLine.mutate({
                  lineId: suggestion.replaces_line_id,
                  body: { variant_id: suggestion.variant_id, source: "upsell" },
                })
              }}
            />
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Deal details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label>Order discount %</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step="0.5"
                  disabled={!editable}
                  value={orderDiscount ?? String(quotation.order_discount_percent)}
                  onChange={(event) => setOrderDiscount(event.target.value)}
                  onBlur={() => {
                    if (orderDiscount === null) return
                    mutations.setOrderDiscount.mutate(Number(orderDiscount) || 0)
                    setOrderDiscount(null)
                  }}
                  className="font-mono tabular-nums"
                />
                <p className="text-xs text-muted-foreground">
                  Added on top of each line&apos;s own discount, then checked
                  against the same ceilings — a header discount cannot bypass
                  them.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label>Notes</Label>
                <Textarea
                  rows={4}
                  disabled={!editable}
                  value={notes ?? quotation.notes ?? ""}
                  onChange={(event) => setNotes(event.target.value)}
                  onBlur={() => {
                    if (notes === null) return
                    mutations.update.mutate({ notes })
                    setNotes(null)
                  }}
                  placeholder="Anything the approver should know."
                />
              </div>

              <dl className="space-y-1.5 border-t pt-4 text-sm">
                <Detail label="Owner" value={quotation.owner_name ?? "—"} />
                <Detail
                  label="Delivery requested"
                  value={
                    quotation.requested_delivery_date
                      ? new Date(
                          quotation.requested_delivery_date
                        ).toLocaleDateString()
                      : "—"
                  }
                />
                <Detail
                  label="Delivery promised"
                  value={
                    quotation.promised_delivery_date
                      ? new Date(
                          quotation.promised_delivery_date
                        ).toLocaleDateString()
                      : "— set when the split is accepted"
                  }
                />
                <Detail
                  label="Valid until"
                  value={
                    quotation.valid_until
                      ? new Date(quotation.valid_until).toLocaleDateString()
                      : "—"
                  }
                />
              </dl>
            </CardContent>
          </Card>

          <NegotiationPanel quotationId={quotation.id} />

          {quotation.approval ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Approval</CardTitle>
                <CardDescription>{quotation.approval.rule_name}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Detail
                  label="Round"
                  value={String(quotation.approval.round_number)}
                />
                <Detail label="Status" value={quotation.approval.status} />
                {quotation.approval.steps.length === 0 ? (
                  <p className="text-muted-foreground">
                    Within every ceiling — no approval was needed.
                  </p>
                ) : (
                  <ol className="space-y-1.5 border-t pt-3">
                    {quotation.approval.steps.map((step) => (
                      <li
                        key={step.id}
                        className="flex items-center justify-between gap-2"
                      >
                        <span className="capitalize">
                          {step.role.replace("_", " ")}
                        </span>
                        <Badge variant="outline">{step.status}</Badge>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}
