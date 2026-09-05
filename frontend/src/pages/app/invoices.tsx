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
import { useInvoiceCounts, useInvoices } from "@/features/billing/use-billing"
import { money } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import { INVOICE_STATUS_LABELS, type InvoiceStatus } from "@/types/api"

const PAGE_SIZE = 20

const TONE: Record<InvoiceStatus, "default" | "secondary" | "destructive" | "outline"> = {
  draft: "outline",
  unpaid: "destructive",
  partially_paid: "secondary",
  paid: "default",
  void: "outline",
}

export default function InvoicesPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<InvoiceStatus | "all">("all")
  const [page, setPage] = useState(1)

  const { data: counts } = useInvoiceCounts()
  const { data, isLoading } = useInvoices({ page, size: PAGE_SIZE, status })

  const pick = (next: InvoiceStatus) => {
    setStatus(status === next ? "all" : next)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Billing"
        title="Invoices"
        description="Every invoice generated from one-time and recurring orders."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Tile
          label="Unpaid"
          value={counts?.unpaid}
          active={status === "unpaid"}
          onClick={() => pick("unpaid")}
        />
        <Tile
          label="Partially paid"
          value={counts?.partially_paid}
          active={status === "partially_paid"}
          onClick={() => pick("partially_paid")}
        />
        <Tile
          label="Paid"
          value={counts?.paid}
          active={status === "paid"}
          onClick={() => pick("paid")}
        />
      </div>

      <Card>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : (data?.items ?? []).length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">
              No invoices yet. One is raised when an order ships, and each
              subscription bills on its own cycle.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Invoice #</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead className="text-right">Paid</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Due date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.items ?? []).map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/app/invoices/${row.id}`)}
                    >
                      <TableCell className="font-mono text-xs">{row.number}</TableCell>
                      <TableCell className="font-medium">{row.customer_name}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.kind === "recurring" ? "Recurring" : "One-time"}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(row.total, row.currency)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                        {money(row.amount_paid, row.currency)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={TONE[row.status]}>
                          {INVOICE_STATUS_LABELS[row.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(row.due_date).toLocaleDateString()}
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
