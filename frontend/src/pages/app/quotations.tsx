import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  LayoutGridIcon,
  PlusIcon,
  SearchIcon,
  TableIcon,
  Trash2Icon,
} from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { SortableHeader } from "@/components/sortable-header"
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
import { NewQuotationDialog } from "@/features/quotations/new-quotation-dialog"
import { money, relativeTime, statusTone } from "@/features/quotations/format"
import { RiskBadge } from "@/features/quotations/risk-badge"
import {
  useQuotationList,
  useQuotationMutations,
  type QuotationListParams,
} from "@/features/quotations/use-quotation"
import { useAuth } from "@/features/auth/use-auth"
import { cn } from "@/lib/utils"
import {
  PIPELINE_STAGES,
  QUOTATION_STAGE_LABELS,
  type QuotationListRow,
  type QuotationSort,
  type QuotationStatus,
} from "@/types/api"

const PAGE_SIZE = 12

export default function QuotationsPage() {
  const navigate = useNavigate()
  const { hasRole } = useAuth()
  const canCreate = hasRole("admin", "sales_rep", "sales_manager")

  const [view, setView] = useState<"cards" | "table">("cards")
  const [stage, setStage] = useState<QuotationStatus | "all">("all")
  const [rawSearch, setRawSearch] = useState("")
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<QuotationSort>("updated")
  const [order, setOrder] = useState<"asc" | "desc">("desc")
  const [creating, setCreating] = useState(false)

  const search = useDebounced(rawSearch, 300)

  const params: QuotationListParams = useMemo(
    () => ({ page, size: PAGE_SIZE, search, status: stage, sort, order }),
    [page, search, stage, sort, order]
  )
  const { data, isLoading } = useQuotationList(params)
  const { remove } = useQuotationMutations(undefined)

  const counts = data?.counts
  const rows = data?.items ?? []

  const toggleSort = (key: QuotationSort) => {
    if (sort === key) {
      setOrder((current) => (current === "asc" ? "desc" : "asc"))
    } else {
      setSort(key)
      setOrder("desc")
    }
    setPage(1)
  }

  const pick = (next: QuotationStatus | "all") => {
    setStage(next)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Sales"
        title="Quotations"
        description="Every quotation in the system. Open one to build it, price it and send it for approval."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to="/app/pipeline">
                <LayoutGridIcon /> Pipeline
              </Link>
            </Button>
            {canCreate ? (
              <Button size="sm" onClick={() => setCreating(true)}>
                <PlusIcon /> New Quotation
              </Button>
            ) : null}
          </div>
        }
      />

      {/* Stage chips. Counts come back with the page, so switching stage costs
          one request rather than one per chip. */}
      <div className="flex flex-wrap items-center gap-2">
        <StageChip
          label="All"
          count={
            counts
              ? Object.values(counts).reduce((sum, value) => sum + value, 0)
              : undefined
          }
          active={stage === "all"}
          onClick={() => pick("all")}
        />
        {PIPELINE_STAGES.map((value) => (
          <StageChip
            key={value}
            label={QUOTATION_STAGE_LABELS[value]}
            count={counts?.[value]}
            active={stage === value}
            onClick={() => pick(value)}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[16rem] flex-1">
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
        <div className="flex items-center rounded-md border p-0.5">
          <Button
            variant={view === "cards" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 px-2"
            onClick={() => setView("cards")}
          >
            <LayoutGridIcon /> Cards
          </Button>
          <Button
            variant={view === "table" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 px-2"
            onClick={() => setView("table")}
          >
            <TableIcon /> Table
          </Button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading quotations…</p>
      ) : rows.length === 0 ? (
        <EmptyState
          hasFilters={Boolean(search) || stage !== "all"}
          onCreate={canCreate ? () => setCreating(true) : undefined}
        />
      ) : view === "cards" ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => (
            <QuotationCard
              key={row.id}
              row={row}
              onOpen={() => navigate(`/app/quotations/${row.id}`)}
              onDelete={
                row.status === "draft" ? () => remove.mutate(row.id) : undefined
              }
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="px-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHeader
                      column="number"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                    >
                      Number
                    </SortableHeader>
                    <SortableHeader
                      column="customer"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                    >
                      Customer
                    </SortableHeader>
                    <TableHead>Owner</TableHead>
                    <SortableHeader
                      column="status"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                    >
                      Stage
                    </SortableHeader>
                    <SortableHeader
                      column="risk"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                    >
                      Risk
                    </SortableHeader>
                    <SortableHeader
                      column="total"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                      className="text-right"
                    >
                      Total
                    </SortableHeader>
                    <SortableHeader
                      column="updated"
                      active={sort}
                      direction={order}
                      onSort={toggleSort}
                    >
                      Last activity
                    </SortableHeader>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/app/quotations/${row.id}`)}
                    >
                      <TableCell className="font-mono text-xs">{row.number}</TableCell>
                      <TableCell className="font-medium">
                        {row.customer_name}
                        {row.customer_tier ? (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {row.customer_tier}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.owner_name ?? "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusTone(row.status)}>
                          {QUOTATION_STAGE_LABELS[row.status]}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <RiskBadge band={row.risk_band} score={row.blended_risk_score} />
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(row.total, row.currency)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {relativeTime(row.last_activity_at ?? row.updated_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {data && data.pages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {data.page} of {data.pages} · {data.total} quotations
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

      <NewQuotationDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}

function StageChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
      )}
    >
      {label}
      {count !== undefined ? (
        <span
          className={cn(
            "rounded-full px-1.5 py-px font-mono text-[10px] tabular-nums",
            active ? "bg-primary-foreground/20" : "bg-muted"
          )}
        >
          {count}
        </span>
      ) : null}
    </button>
  )
}

function QuotationCard({
  row,
  onOpen,
  onDelete,
}: {
  row: QuotationListRow
  onOpen: () => void
  onDelete?: () => void
}) {
  return (
    <Card
      className="group cursor-pointer transition-colors hover:border-foreground/25"
      onClick={onOpen}
    >
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-medium">{row.customer_name}</p>
            <p className="font-mono text-xs text-muted-foreground">{row.number}</p>
          </div>
          <Badge variant={statusTone(row.status)}>
            {QUOTATION_STAGE_LABELS[row.status]}
          </Badge>
        </div>

        <p className="font-mono text-2xl tabular-nums">
          {money(row.total, row.currency)}
        </p>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <RiskBadge band={row.risk_band} score={row.blended_risk_score} />
          <span>
            {row.line_count} {row.line_count === 1 ? "line" : "lines"}
          </span>
          {row.customer_tier ? <span>· {row.customer_tier}</span> : null}
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Updated {relativeTime(row.last_activity_at ?? row.updated_at)}</span>
          {onDelete ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 opacity-0 transition-opacity group-hover:opacity-100"
              onClick={(event) => {
                event.stopPropagation()
                onDelete()
              }}
            >
              <Trash2Icon />
              <span className="sr-only">Delete draft</span>
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function EmptyState({
  hasFilters,
  onCreate,
}: {
  hasFilters: boolean
  onCreate?: () => void
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm font-medium">
          {hasFilters ? "Nothing matches those filters" : "No quotations yet"}
        </p>
        <p className="max-w-sm text-sm text-muted-foreground">
          {hasFilters
            ? "Try a different stage, or clear the search."
            : "Start one for a customer and add products, discounts and upsells."}
        </p>
        {!hasFilters && onCreate ? (
          <Button size="sm" onClick={onCreate}>
            <PlusIcon /> New Quotation
          </Button>
        ) : null}
      </CardContent>
    </Card>
  )
}
