import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { InboxIcon, SearchIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useDebounced } from "@/hooks/use-debounced"
import {
  useApprovalList,
  type ApprovalListParams,
} from "@/features/approvals/use-approvals"
import { money, relativeTime } from "@/features/quotations/format"
import { RiskBadge } from "@/features/quotations/risk-badge"
import { cn } from "@/lib/utils"
import { ROLE_LABELS, type ApprovalStatus } from "@/types/api"

const PAGE_SIZE = 15

const STATUS_TONE: Record<ApprovalStatus, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "secondary",
  approved: "default",
  auto_approved: "outline",
  returned: "secondary",
  rejected: "destructive",
  cancelled: "outline",
}

const STATUS_LABEL: Record<ApprovalStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  auto_approved: "Auto-Approved",
  returned: "Returned",
  rejected: "Rejected",
  cancelled: "Cancelled",
}

export default function ApprovalsPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<ApprovalStatus | "all">("all")
  const [mine, setMine] = useState(false)
  const [rawSearch, setRawSearch] = useState("")
  const [page, setPage] = useState(1)

  const search = useDebounced(rawSearch, 300)
  const params: ApprovalListParams = useMemo(
    () => ({ page, size: PAGE_SIZE, status, mine, search }),
    [page, status, mine, search]
  )
  const { data, isLoading } = useApprovalList(params)

  const counts = data?.counts
  const rows = data?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Governance"
        title="Approvals"
        description="Every quotation that needed, needs, or went through discount approval."
        actions={
          <Button
            variant={mine ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setMine((current) => !current)
              setPage(1)
            }}
          >
            <InboxIcon /> {mine ? "Waiting on me" : "Everything"}
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <CountTile
          label="Pending"
          value={counts?.pending}
          active={status === "pending"}
          onClick={() => {
            setStatus(status === "pending" ? "all" : "pending")
            setPage(1)
          }}
        />
        <CountTile
          label="Returned"
          value={counts?.returned}
          active={status === "returned"}
          onClick={() => {
            setStatus(status === "returned" ? "all" : "returned")
            setPage(1)
          }}
        />
        <CountTile
          label="Approved"
          value={counts?.approved}
          active={status === "approved"}
          onClick={() => {
            setStatus(status === "approved" ? "all" : "approved")
            setPage(1)
          }}
        />
        <CountTile
          label="Rejected"
          value={counts?.rejected}
          active={status === "rejected"}
          onClick={() => {
            setStatus(status === "rejected" ? "all" : "rejected")
            setPage(1)
          }}
        />
      </div>

      <div className="relative max-w-md">
        <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={rawSearch}
          onChange={(event) => {
            setRawSearch(event.target.value)
            setPage(1)
          }}
          placeholder="Search by number or customer"
          className="pl-8"
        />
      </div>

      <Card>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading approvals…</p>
          ) : rows.length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">
              {mine
                ? "Nothing is waiting on you."
                : "No approvals match those filters."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Quotation</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Blended risk</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Submitted by</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead>Submitted</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow
                      key={row.id}
                      className={cn("cursor-pointer", row.can_act && "bg-brass/[0.05]")}
                      onClick={() => navigate(`/app/approvals/${row.id}`)}
                    >
                      <TableCell className="font-mono text-xs">
                        {row.quotation_number}
                        {row.round_number > 1 ? (
                          <span className="ml-1.5 text-muted-foreground">
                            r{row.round_number}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="font-medium">
                        {row.customer_name}
                        {row.customer_tier ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {row.customer_tier}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <RiskBadge band={row.risk_band} score={row.blended_risk_score} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Badge variant={STATUS_TONE[row.status]}>
                            {STATUS_LABEL[row.status]}
                          </Badge>
                          {row.current_role ? (
                            <span className="text-xs text-muted-foreground">
                              {ROLE_LABELS[row.current_role]}
                            </span>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.submitted_by_name}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(row.quotation_total, row.currency)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {relativeTime(row.submitted_at)}
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
            Page {data.page} of {data.pages} · {data.total} rounds
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={data.page <= 1}
              onClick={() => setPage((current) => current - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={data.page >= data.pages}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function CountTile({
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
