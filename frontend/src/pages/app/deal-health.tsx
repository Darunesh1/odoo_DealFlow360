import { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  BellIcon,
  CheckIcon,
  RefreshCwIcon,
  SearchIcon,
  TrendingUpIcon,
  TriangleAlertIcon,
} from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
  useAlertActions,
  useAlertCounts,
  useAlerts,
} from "@/features/analytics/use-analytics"
import { relativeTime } from "@/features/quotations/format"
import { RiskBadge } from "@/features/quotations/risk-badge"
import { ALERT_TYPE_LABELS } from "@/types/api"

export default function DealHealthPage() {
  const navigate = useNavigate()
  const { hasRole } = useAuth()
  const canAct = hasRole("admin", "sales_manager", "finance")

  const { data: counts } = useAlertCounts()
  const { data: alerts, isLoading, isError } = useAlerts()
  const { sweep, act } = useAlertActions()
  const [busy, setBusy] = useState<string | null>(null)

  const run = (
    alertId: string,
    action: "nudge" | "escalate" | "resolve"
  ) => {
    setBusy(alertId)
    act.mutate({ alertId, action }, { onSettled: () => setBusy(null) })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Governance"
        title="Deal health"
        description={
          counts?.last_swept_at
            ? `Last checked ${relativeTime(counts.last_swept_at)}. Stalled deals, unusual discounts and delivery promises the fulfillment no longer supports.`
            : "Stalled deals, unusual discounts and delivery promises the fulfillment no longer supports."
        }
        actions={
          // Only the roles POST /alerts/sweep admits. A rep used to see this
          // button and get a 403 toast from it.
          canAct ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => sweep.mutate()}
              disabled={sweep.isPending}
            >
              <RefreshCwIcon /> Run detection now
            </Button>
          ) : null
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Tile
          label="Stalled deals"
          value={counts?.stalled_deals}
          hint="Idle beyond the configured window"
        />
        <Tile
          label="Discount anomalies"
          value={counts?.discount_anomalies}
          hint="Well above that rep's own average"
        />
        <Tile
          label="Delivery slippage"
          value={counts?.delivery_slippage}
          hint="Promise dates the split cannot meet"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Open alerts</CardTitle>
          <CardDescription>
            Click a row to open the deal. Nudging emails the rep; escalating
            emails their manager.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : isError ? (
            // A failed request used to render as the reassuring green block,
            // which is the one thing it must never say.
            <div className="px-6 py-12 text-center">
              <TriangleAlertIcon className="mx-auto size-6 text-amber-600 dark:text-amber-400" />
              <p className="mt-2 text-sm font-medium">Could not load alerts</p>
              <p className="text-sm text-muted-foreground">
                The deal health check is unavailable, so this is not a clean
                bill of health. Try again in a moment.
              </p>
            </div>
          ) : (alerts ?? []).length === 0 ? (
            counts?.last_swept_at ? (
              <div className="px-6 py-12 text-center">
                <TrendingUpIcon className="mx-auto size-6 text-emerald-600 dark:text-emerald-400" />
                <p className="mt-2 text-sm font-medium">Nothing is at risk</p>
                <p className="text-sm text-muted-foreground">
                  Every live deal is moving and every promise is still achievable.
                </p>
              </div>
            ) : (
              // Never swept is not the same as nothing wrong.
              <div className="px-6 py-12 text-center">
                <SearchIcon className="mx-auto size-6 text-muted-foreground" />
                <p className="mt-2 text-sm font-medium">
                  Detection has not run yet
                </p>
                <p className="text-sm text-muted-foreground">
                  No deal has been checked, so this is not a clean bill of
                  health.
                  {canAct ? " Run detection to see where things stand." : ""}
                </p>
                {canAct ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={() => sweep.mutate()}
                    disabled={sweep.isPending}
                  >
                    <RefreshCwIcon /> Run detection now
                  </Button>
                ) : null}
              </div>
            )
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Deal</TableHead>
                    <TableHead>Issue</TableHead>
                    <TableHead>Detail</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead>Flagged</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(alerts ?? []).map((alert) => (
                    <TableRow key={alert.id}>
                      <TableCell
                        className="cursor-pointer"
                        onClick={() =>
                          navigate(`/app/quotations/${alert.quotation_id}`)
                        }
                      >
                        <p className="font-medium">{alert.customer_name}</p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {alert.quotation_number}
                        </p>
                      </TableCell>
                      <TableCell>
                        <RiskBadge band={alert.severity} />
                        <span className="ml-2 text-sm">
                          {ALERT_TYPE_LABELS[alert.alert_type]}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {alert.detail}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {alert.owner_name ?? "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {relativeTime(alert.flagged_at)}
                      </TableCell>
                      <TableCell className="capitalize text-muted-foreground">
                        {alert.status}
                      </TableCell>
                      <TableCell className="text-right">
                        {canAct ? (
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7"
                              disabled={busy === alert.id}
                              onClick={() => run(alert.id, "nudge")}
                            >
                              <BellIcon className="size-3.5" /> Nudge
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7"
                              disabled={busy === alert.id}
                              onClick={() => run(alert.id, "escalate")}
                            >
                              Escalate
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7"
                              disabled={busy === alert.id}
                              onClick={() => run(alert.id, "resolve")}
                            >
                              <CheckIcon className="size-3.5" />
                            </Button>
                          </div>
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
    </div>
  )
}

function Tile({
  label,
  value,
  hint,
}: {
  label: string
  value?: number
  hint: string
}) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="label-mono text-muted-foreground">{label}</p>
        <p className="font-mono text-2xl tabular-nums">{value ?? "—"}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}
