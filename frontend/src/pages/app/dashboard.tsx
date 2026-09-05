import { Link } from "react-router-dom"
import {
  ArrowRightIcon,
  FileMinusIcon,
  FileTextIcon,
  GavelIcon,
  PlusIcon,
  ReceiptIcon,
  RotateCcwIcon,
  TrendingUpIcon,
  TriangleAlertIcon,
  TruckIcon,
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
import type { ActivityEntry, DashboardData } from "@/types/api"

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

/**
 * What each role actually needs to see first thing.
 *
 * Every figure comes from the same query as the screen its tile links to, so
 * clicking a number lands on a list showing that number. The dashboard used to
 * count company-wide while every list was owner-scoped, which meant a rep read
 * "4 pending approvals" and then opened an empty inbox.
 */
function tilesFor(data: DashboardData | undefined) {
  const money0 = (value: number) => money(value)

  switch (data?.role) {
    case "rep":
      return [
        { label: "My open quotations", value: data.open_quotations, hint: "still in play", to: "/app/quotations", icon: FileTextIcon },
        { label: "Awaiting approval", value: data.awaiting_approval, hint: "submitted, undecided", to: "/app/approvals?status=pending", icon: GavelIcon },
        { label: "Returned to me", value: data.returned_to_me, hint: "needs a revision", to: "/app/approvals?status=returned", icon: RotateCcwIcon, alarming: data.returned_to_me > 0 },
        { label: "My pipeline", value: money0(data.pipeline_value), hint: "not yet confirmed", to: "/app/pipeline", icon: TrendingUpIcon },
      ]
    case "manager":
      return [
        { label: "Waiting on me", value: data.waiting_on_me, hint: "my decision", to: "/app/approvals", icon: GavelIcon, alarming: data.waiting_on_me > 0 },
        { label: "Open quotations", value: data.open_quotations, hint: "across the team", to: "/app/quotations", icon: FileTextIcon },
        { label: "At-risk deals", value: data.at_risk_deals, hint: "flagged by deal health", to: "/app/deal-health", icon: TriangleAlertIcon, alarming: data.at_risk_deals > 0 },
        { label: "Pipeline", value: money0(data.pipeline_value), hint: "not yet confirmed", to: "/app/pipeline", icon: TrendingUpIcon },
      ]
    case "finance":
      return [
        { label: "Splits to accept", value: data.splits_to_accept, hint: "stock not yet reserved", to: "/app/fulfillment", icon: TruckIcon, alarming: data.splits_to_accept > 0 },
        { label: "Unpaid invoices", value: data.unpaid_invoices, hint: "outstanding or part-paid", to: "/app/invoices?status=unpaid", icon: ReceiptIcon },
        { label: "Owed to us", value: money0(data.outstanding_amount), hint: "across every open invoice", to: "/app/invoices", icon: TrendingUpIcon },
        { label: "Credits to apply", value: data.credits_to_apply, hint: "owed back to customers", to: "/app/credit-notes", icon: FileMinusIcon, alarming: data.credits_to_apply > 0 },
      ]
    default:
      return [
        { label: "Pending approvals", value: data?.pending_approvals ?? 0, hint: "waiting on a decision", to: "/app/approvals", icon: GavelIcon },
        { label: "Open quotations", value: data?.open_quotations ?? 0, hint: "active deals", to: "/app/quotations", icon: FileTextIcon },
        { label: "At-risk deals", value: data?.at_risk_deals ?? 0, hint: "flagged by deal health", to: "/app/deal-health", icon: TriangleAlertIcon, alarming: Boolean(data?.at_risk_deals) },
        { label: "Pipeline value", value: money0(data?.pipeline_value ?? 0), hint: "not yet confirmed", to: "/app/pipeline", icon: TrendingUpIcon },
      ]
  }
}

export default function DashboardPage() {
  const { user, hasRole } = useAuth()
  const { data, isLoading } = useDashboard()
  const canQuote = hasRole("admin", "sales_rep", "sales_manager")
  const tiles = tilesFor(data)

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
        {tiles.map((tile) => (
          <Tile key={tile.label} {...tile} loading={isLoading} />
        ))}
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
