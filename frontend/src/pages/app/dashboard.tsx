import { Link } from "react-router-dom"
import {
  ArrowRightIcon,
  FileTextIcon,
  GavelIcon,
  PlusIcon,
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
import { useAuth } from "@/features/auth/use-auth"
import { useDashboard } from "@/features/analytics/use-analytics"
import { money, relativeTime } from "@/features/quotations/format"
import type { ActivityEntry } from "@/types/api"

/** Where an audit entry points, so a row in the feed is clickable. */
function entityHref(entry: ActivityEntry) {
  switch (entry.entity_type) {
    case "quotation":
      return `/app/quotations/${entry.entity_id}`
    case "approval":
      return `/app/approvals/${entry.entity_id}`
    case "invoice":
      return `/app/invoices/${entry.entity_id}`
    case "fulfillment":
      return `/app/fulfillment/${entry.entity_id}`
    default:
      return null
  }
}

function describe(entry: ActivityEntry) {
  const number =
    typeof entry.context?.quotation_number === "string"
      ? entry.context.quotation_number
      : null
  const action = entry.action.replace(/_/g, " ")
  return `${entry.actor_name} ${action}${number ? ` ${number}` : ""}`
}

export default function DashboardPage() {
  const { user, hasRole } = useAuth()
  const { data, isLoading } = useDashboard()
  const canQuote = hasRole("admin", "sales_rep", "sales_manager")

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Sales"
        title={`Welcome back${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}`}
        description="Everything in flight, and what needs a decision today."
        actions={
          canQuote ? (
            <Button size="sm" asChild>
              <Link to="/app/quotations">
                <PlusIcon /> New quotation
              </Link>
            </Button>
          ) : null
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="Pending approvals"
          value={data?.pending_approvals}
          hint="waiting on a decision"
          to="/app/approvals"
          icon={GavelIcon}
          loading={isLoading}
        />
        <Tile
          label="Open quotations"
          value={data?.open_quotations}
          hint="active deals"
          to="/app/quotations"
          icon={FileTextIcon}
          loading={isLoading}
        />
        <Tile
          label="At-risk deals"
          value={data?.at_risk_deals}
          hint="flagged by deal health"
          to="/app/deal-health"
          icon={TriangleAlertIcon}
          loading={isLoading}
          alarming={Boolean(data?.at_risk_deals)}
        />
        <Tile
          label="Pipeline value"
          value={data ? money(data.pipeline_value) : undefined}
          hint="not yet confirmed"
          to="/app/pipeline"
          icon={TrendingUpIcon}
          loading={isLoading}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent activity</CardTitle>
          <CardDescription>
            Every submission, decision, despatch and payment, newest first.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (data?.recent_activity ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing has happened yet. Build a quotation and it will show up
              here.
            </p>
          ) : (
            (data?.recent_activity ?? []).map((entry) => {
              const href = entityHref(entry)
              const body = (
                <div className="flex items-start justify-between gap-3 rounded-lg border p-3 transition-colors hover:border-foreground/25">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{describe(entry)}</p>
                    {entry.reason ? (
                      <p className="truncate text-sm text-muted-foreground">
                        {entry.reason}
                      </p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {relativeTime(entry.created_at)}
                  </span>
                </div>
              )
              return href ? (
                <Link key={entry.id} to={href} className="block">
                  {body}
                </Link>
              ) : (
                <div key={entry.id}>{body}</div>
              )
            })
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
  to,
  icon: Icon,
  loading,
  alarming,
}: {
  label: string
  value?: number | string
  hint: string
  to: string
  icon: typeof GavelIcon
  loading: boolean
  alarming?: boolean
}) {
  return (
    <Link to={to}>
      <Card className="h-full transition-colors hover:border-foreground/25">
        <CardContent className="space-y-1">
          <div className="flex items-center justify-between">
            <p className="label-mono text-muted-foreground">{label}</p>
            <Icon
              className={
                alarming
                  ? "size-4 text-amber-600 dark:text-amber-400"
                  : "size-4 text-muted-foreground"
              }
            />
          </div>
          <p className="font-mono text-2xl tabular-nums">
            {loading ? "—" : (value ?? 0)}
          </p>
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            {hint} <ArrowRightIcon className="size-3" />
          </p>
        </CardContent>
      </Card>
    </Link>
  )
}
