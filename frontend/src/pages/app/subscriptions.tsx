import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  useSubscriptionCounts,
  useSubscriptions,
} from "@/features/billing/use-billing"
import { money } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import type { SubscriptionStatus } from "@/types/api"

const PAGE_SIZE = 20

const TONE: Record<SubscriptionStatus, "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  paused: "secondary",
  cancelled: "destructive",
  expired: "outline",
}

export default function SubscriptionsPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<SubscriptionStatus | "all">("all")
  const [page, setPage] = useState(1)

  const { data: counts } = useSubscriptionCounts()
  const { data, isLoading } = useSubscriptions({ page, size: PAGE_SIZE, status })

  const pick = (next: SubscriptionStatus) => {
    setStatus(status === next ? "all" : next)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Billing"
        title="Subscriptions"
        description="Every recurring plan across every customer, whichever order it came from."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Active" value={counts?.active} active={status === "active"} onClick={() => pick("active")} />
        <Tile label="Paused" value={counts?.paused} active={status === "paused"} onClick={() => pick("paused")} />
        <Tile
          label="Cancelled"
          value={counts?.cancelled}
          active={status === "cancelled"}
          onClick={() => pick("cancelled")}
        />
      </div>

      <Card>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : (data?.items ?? []).length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">
              No subscriptions yet. Confirming an order with a recurring line
              opens one.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Customer</TableHead>
                    <TableHead>Plan</TableHead>
                    <TableHead>Cycle</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead>Next bill</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.items ?? []).map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/app/subscriptions/${row.id}`)}
                    >
                      <TableCell className="font-medium">{row.customer_name}</TableCell>
                      <TableCell>{row.plan_name}</TableCell>
                      <TableCell className="capitalize text-muted-foreground">
                        {row.interval}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {row.quantity}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(row.unit_price * row.quantity, row.currency)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {/* Null is the mockup's "-": a paused plan has no next date. */}
                        {row.next_billing_date
                          ? new Date(row.next_billing_date).toLocaleDateString()
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={TONE[row.status]}>{row.status}</Badge>
                        {row.cancel_at_period_end && row.status === "active" ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            ends this period
                          </span>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {data && data.pages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {data.page} of {data.pages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={data.page <= 1}
              onClick={() => setPage((c) => c - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={data.page >= data.pages}
              onClick={() => setPage((c) => c + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function Tile({
  label,
  value,
  active,
  onClick,
}: {
  label: string
  value?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} className="text-left">
      <Card className={cn("transition-colors", active && "border-primary")}>
        <CardContent className="space-y-1">
          <p className="label-mono text-muted-foreground">{label}</p>
          <p className="font-mono text-2xl tabular-nums">{value ?? "—"}</p>
        </CardContent>
      </Card>
    </button>
  )
}
