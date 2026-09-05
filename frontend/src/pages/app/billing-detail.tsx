import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeftIcon, ExternalLinkIcon, PauseIcon, PlayIcon, XIcon } from "lucide-react"

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
import { useAuth } from "@/features/auth/use-auth"
import {
  useSubscription,
  useSubscriptionActions,
} from "@/features/billing/use-billing"
import { money } from "@/features/quotations/format"

export default function BillingDetailPage() {
  const { subscriptionId } = useParams<{ subscriptionId: string }>()
  const { hasRole } = useAuth()
  const canManage = hasRole("admin", "finance")

  const { data: subscription, isLoading } = useSubscription(subscriptionId)
  const actions = useSubscriptionActions(subscriptionId)
  const [quantity, setQuantity] = useState("")
  const [effective, setEffective] = useState("")

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }
  if (!subscription) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          That subscription does not exist.
        </CardContent>
      </Card>
    )
  }

  const oneTimeTotal = subscription.one_time_lines.reduce(
    (sum, line) => sum + line.amount,
    0
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/app/subscriptions"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> Subscriptions
          </Link>
        }
        title={`${subscription.customer_name} · ${subscription.plan_name}`}
        description="One-time and recurring lines from the same order, billed separately."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to={`/app/quotations/${subscription.quotation_id}`}>
              <ExternalLinkIcon /> {subscription.quotation_number}
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={subscription.status === "active" ? "default" : "secondary"}>
          {subscription.status}
        </Badge>
        <span className="text-sm capitalize text-muted-foreground">
          {subscription.interval} · {subscription.quantity} ×{" "}
          {money(subscription.unit_price, subscription.currency)}
        </span>
        <span className="text-sm text-muted-foreground">
          · current period {subscription.current_period_start} to{" "}
          {subscription.current_period_end}
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">One-time lines</CardTitle>
              <CardDescription>
                From the originating order. Billed once, on despatch.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {subscription.one_time_lines.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-muted-foreground">
                        This order is subscription-only.
                      </TableCell>
                    </TableRow>
                  ) : (
                    <>
                      {subscription.one_time_lines.map((line) => (
                        <TableRow key={line.id}>
                          <TableCell>{line.description}</TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {line.quantity}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {money(line.amount, subscription.currency)}
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow>
                        <TableCell colSpan={2} className="font-medium">
                          Total
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium tabular-nums">
                          {money(oneTimeTotal, subscription.currency)}
                        </TableCell>
                      </TableRow>
                    </>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recurring lines</CardTitle>
              <CardDescription>
                Every plan on this order, with its own cycle and next bill date.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Plan</TableHead>
                    <TableHead>Cycle</TableHead>
                    <TableHead>Next bill</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {subscription.recurring_lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell className="font-medium">{line.plan_name}</TableCell>
                      <TableCell className="capitalize text-muted-foreground">
                        {line.interval}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {line.next_billing_date
                          ? new Date(line.next_billing_date).toLocaleDateString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(line.unit_price * line.quantity, line.currency)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Proration history</CardTitle>
              <CardDescription>
                Every mid-cycle change, with the arithmetic that produced its
                charge or credit.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead>
                      <TableHead>Effective</TableHead>
                      <TableHead>Change</TableHead>
                      <TableHead className="text-right">Days left</TableHead>
                      <TableHead className="text-right">Factor</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {subscription.events.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          No changes yet.
                        </TableCell>
                      </TableRow>
                    ) : (
                      subscription.events.map((event) => (
                        <TableRow key={event.id}>
                          <TableCell className="capitalize">
                            {event.event_type.replace(/_/g, " ")}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {new Date(event.effective_date).toLocaleDateString()}
                          </TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">
                            {event.previous_quantity !== null
                              ? `${event.previous_quantity} → ${event.new_quantity}`
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                            {event.days_remaining !== null
                              ? `${event.days_remaining}/${event.days_in_period}`
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                            {event.proration_factor !== null
                              ? event.proration_factor.toFixed(4)
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums">
                            {event.proration_amount !== null ? (
                              <span
                                className={
                                  event.proration_amount < 0
                                    ? "text-emerald-600 dark:text-emerald-400"
                                    : ""
                                }
                              >
                                {money(event.proration_amount, subscription.currency)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Upcoming billing</CardTitle>
              <CardDescription>
                Projected from the cycle — future periods are arithmetic, not
                rows a cancellation would have to delete.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {subscription.upcoming.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing scheduled while it is {subscription.status}.
                </p>
              ) : (
                subscription.upcoming.map((bill) => (
                  <div
                    key={bill.period_start}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-muted-foreground">
                      {new Date(bill.period_start).toLocaleDateString()}
                    </span>
                    <span className="font-mono tabular-nums">
                      {money(bill.amount, subscription.currency)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {canManage ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Modify subscription</CardTitle>
                <CardDescription>
                  A change mid-period is prorated for the days not yet used.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1.5">
                  <Label>New quantity</Label>
                  <Input
                    type="number"
                    min={1}
                    value={quantity}
                    onChange={(event) => setQuantity(event.target.value)}
                    placeholder={String(subscription.quantity)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Effective from</Label>
                  <Input
                    type="date"
                    value={effective}
                    onChange={(event) => setEffective(event.target.value)}
                  />
                </div>
                <Button
                  className="w-full"
                  disabled={!quantity || actions.changeQuantity.isPending}
                  onClick={() =>
                    actions.changeQuantity.mutate(
                      {
                        quantity: Number(quantity),
                        effective_date: effective || undefined,
                      },
                      { onSuccess: () => setQuantity("") }
                    )
                  }
                >
                  Apply change
                </Button>

                <div className="grid gap-2 border-t pt-3">
                  {subscription.status === "active" ? (
                    <Button
                      variant="outline"
                      onClick={() => actions.pause.mutate()}
                      disabled={actions.pause.isPending}
                    >
                      <PauseIcon /> Pause
                    </Button>
                  ) : subscription.status === "paused" ? (
                    <Button
                      variant="outline"
                      onClick={() => actions.resume.mutate()}
                      disabled={actions.resume.isPending}
                    >
                      <PlayIcon /> Resume
                    </Button>
                  ) : null}

                  {subscription.status !== "cancelled" ? (
                    <>
                      <Button
                        variant="outline"
                        onClick={() =>
                          actions.cancel.mutate({ at_period_end: true })
                        }
                        disabled={actions.cancel.isPending}
                      >
                        Cancel at period end
                      </Button>
                      <Button
                        variant="outline"
                        className="text-destructive hover:text-destructive"
                        onClick={() =>
                          actions.cancel.mutate({ at_period_end: false })
                        }
                        disabled={actions.cancel.isPending}
                      >
                        <XIcon /> Cancel now and credit
                      </Button>
                    </>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
