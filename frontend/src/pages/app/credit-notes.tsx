import { useState } from "react"
import { Link } from "react-router-dom"
import { ReceiptIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
  useApplyCreditNote,
  useCreditNoteCounts,
  useCreditNotes,
  useInvoices,
} from "@/features/billing/use-billing"
import { money, relativeTime } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import type { CreditNote, CreditNoteStatus } from "@/types/api"

const TONE: Record<CreditNoteStatus, "default" | "secondary" | "destructive" | "outline"> = {
  draft: "outline",
  issued: "secondary",
  applied: "default",
  cancelled: "outline",
}

export default function CreditNotesPage() {
  const { hasRole } = useAuth()
  const canApply = hasRole("admin", "finance")

  const { data: notes, isLoading } = useCreditNotes()
  const { data: counts } = useCreditNoteCounts()
  const [applying, setApplying] = useState<CreditNote | null>(null)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Billing"
        title="Credit notes"
        description="What the business owes back, and why. Raised automatically when a subscription is reduced or cancelled part-way through a period."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Outstanding" value={counts?.issued} hint="not yet applied" />
        <Tile label="Applied" value={counts?.applied} hint="settled against an invoice" />
        <Tile
          label="Owed"
          value={
            counts ? money(counts.outstanding_amount) : undefined
          }
          hint="total still to credit"
        />
      </div>

      <Card>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : (notes ?? []).length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">
              Nothing credited yet. Reducing or cancelling a subscription
              mid-period raises one automatically.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Note</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Issued</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(notes ?? []).map((note) => (
                    <TableRow key={note.id}>
                      <TableCell className="font-mono text-xs">{note.number}</TableCell>
                      <TableCell className="font-medium">
                        {note.customer_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {note.reason ?? "—"}
                        {note.plan_name ? (
                          <p className="text-xs">from {note.plan_name}</p>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(note.amount, note.currency)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={TONE[note.status]}>{note.status}</Badge>
                        {note.invoice_number ? (
                          <Link
                            to={`/app/invoices/${note.invoice_id}`}
                            className="ml-2 text-xs underline underline-offset-4"
                          >
                            {note.invoice_number}
                          </Link>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {relativeTime(note.issued_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {canApply && note.status === "issued" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7"
                            onClick={() => setApplying(note)}
                          >
                            <ReceiptIcon /> Apply
                          </Button>
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

      <ApplyDialog note={applying} onClose={() => setApplying(null)} />
    </div>
  )
}

function ApplyDialog({
  note,
  onClose,
}: {
  note: CreditNote | null
  onClose: () => void
}) {
  const apply = useApplyCreditNote()
  const { data: invoices } = useInvoices({ page: 1, size: 100 })

  // Only this customer's unpaid invoices, and only ones with enough
  // outstanding to absorb the note — the server refuses a partial application
  // because the note has nowhere to record a remainder.
  const candidates = (invoices?.items ?? []).filter(
    (invoice) =>
      note !== null &&
      invoice.customer_id === note.customer_id &&
      invoice.status !== "paid" &&
      invoice.status !== "void" &&
      invoice.currency === note.currency &&
      invoice.total - invoice.amount_paid >= note.amount
  )

  return (
    <Dialog open={note !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Apply {note?.number}</DialogTitle>
          <DialogDescription>
            {note
              ? `${money(note.amount, note.currency)} owed to ${note.customer_name}. Pick an invoice to settle it against.`
              : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          {candidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {note?.customer_name} has no outstanding invoice large enough to
              absorb this credit. It stays owed until they do.
            </p>
          ) : (
            candidates.map((invoice) => (
              <button
                key={invoice.id}
                type="button"
                className="flex w-full items-center justify-between rounded-lg border p-3 text-left text-sm transition-colors hover:border-foreground/25"
                disabled={apply.isPending}
                onClick={() =>
                  note &&
                  apply.mutate(
                    { noteId: note.id, invoiceId: invoice.id },
                    { onSuccess: onClose }
                  )
                }
              >
                <span>
                  <span className="font-mono text-xs">{invoice.number}</span>
                  <span className="ml-2 text-muted-foreground">
                    due {new Date(invoice.due_date).toLocaleDateString()}
                  </span>
                </span>
                <span className="font-mono tabular-nums">
                  {money(invoice.total - invoice.amount_paid, invoice.currency)}{" "}
                  <span className="text-xs text-muted-foreground">outstanding</span>
                </span>
              </button>
            ))
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Tile({
  label,
  value,
  hint,
}: {
  label: string
  value?: number | string
  hint: string
}) {
  return (
    <Card>
      <CardContent className={cn("space-y-1")}>
        <p className="label-mono text-muted-foreground">{label}</p>
        <p className="font-mono text-2xl tabular-nums">{value ?? "—"}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}
