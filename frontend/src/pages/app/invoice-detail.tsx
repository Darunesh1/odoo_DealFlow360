import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  ArrowLeftIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  ExternalLinkIcon,
  WalletIcon,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/features/auth/use-auth"
import { useInvoice, useRecordPayment } from "@/features/billing/use-billing"
import { money } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import {
  INVOICE_STATUS_LABELS,
  PAYMENT_METHODS,
  PAYMENT_METHOD_LABELS,
  type PaymentMethod,
} from "@/types/api"

export default function InvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const { hasRole } = useAuth()
  const canRecord = hasRole("admin", "finance")

  const { data: invoice, isLoading } = useInvoice(invoiceId)
  const record = useRecordPayment(invoiceId)

  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState("")
  const [method, setMethod] = useState<PaymentMethod>("bank_transfer")
  const [reference, setReference] = useState("")

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>
  if (!invoice) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          That invoice does not exist.
        </CardContent>
      </Card>
    )
  }

  const outstanding = Number((invoice.total - invoice.amount_paid).toFixed(2))

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/app/invoices"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> Invoices
          </Link>
        }
        title={`${invoice.number} · ${invoice.customer_name}`}
        description="Partial invoicing stays reconciled with partial delivery — nothing is billed before it ships."
        actions={
          <div className="flex items-center gap-2">
            {invoice.quotation_id ? (
              <Button variant="outline" size="sm" asChild>
                <Link to={`/app/quotations/${invoice.quotation_id}`}>
                  <ExternalLinkIcon /> {invoice.quotation_number}
                </Link>
              </Button>
            ) : null}
            {canRecord && outstanding > 0 ? (
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <WalletIcon /> Record payment
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Record a payment</DialogTitle>
                    <DialogDescription>
                      {money(outstanding, invoice.currency)} is outstanding on{" "}
                      {invoice.number}.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <Label>Amount</Label>
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={amount}
                        onChange={(event) => setAmount(event.target.value)}
                        placeholder={String(outstanding)}
                        className="font-mono tabular-nums"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Method</Label>
                      <Select
                        value={method}
                        onValueChange={(value) => setMethod(value as PaymentMethod)}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PAYMENT_METHODS.map((value) => (
                            <SelectItem key={value} value={value}>
                              {PAYMENT_METHOD_LABELS[value]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Reference</Label>
                      <Input
                        value={reference}
                        onChange={(event) => setReference(event.target.value)}
                        placeholder="NEFT-88213"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>
                      Cancel
                    </Button>
                    <Button
                      disabled={!amount || record.isPending}
                      onClick={() =>
                        record.mutate(
                          {
                            amount: Number(amount),
                            method,
                            reference: reference || undefined,
                          },
                          {
                            onSuccess: () => {
                              setOpen(false)
                              setAmount("")
                              setReference("")
                            },
                          }
                        )
                      }
                    >
                      Record payment
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            ) : null}
          </div>
        }
      />

      {/* Derived from what actually happened to the order, not from a status
          column that could disagree with it. */}
      <Card>
        <CardContent className="flex flex-wrap gap-6 py-4">
          <Step label="Order confirmed" done={invoice.order_confirmed} />
          <Step label="Shipped" done={invoice.order_shipped} />
          <Step label="Invoiced" done={invoice.order_invoiced} />
          <Step label="Paid" done={invoice.order_paid} />
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Lines</CardTitle>
            </CardHeader>
            <CardContent className="px-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Description</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Unit</TableHead>
                      <TableHead className="text-right">Tax</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoice.lines.map((line) => (
                      <TableRow key={line.id}>
                        <TableCell>
                          {line.description}
                          {line.line_type !== "one_time" ? (
                            <Badge variant="outline" className="ml-2 capitalize">
                              {line.line_type.replace(/_/g, " ")}
                            </Badge>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {line.quantity}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {money(line.unit_price, invoice.currency)}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                          {money(line.tax_amount, invoice.currency)}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {money(line.line_total, invoice.currency)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Payments</CardTitle>
              <CardDescription>
                The invoice&apos;s paid amount is always the sum of these, never a
                typed figure.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Received</TableHead>
                    <TableHead>Method</TableHead>
                    <TableHead>Reference</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoice.payments.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-muted-foreground">
                        Nothing received yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    invoice.payments.map((payment) => (
                      <TableRow key={payment.id}>
                        <TableCell className="text-muted-foreground">
                          {new Date(payment.received_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell>{PAYMENT_METHOD_LABELS[payment.method]}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {payment.reference ?? "—"}
                        </TableCell>
                        <TableCell
                          className={cn(
                            "text-right font-mono tabular-nums",
                            payment.is_refund && "text-destructive"
                          )}
                        >
                          {payment.is_refund ? "−" : ""}
                          {money(payment.amount, invoice.currency)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Status">
                <Badge
                  variant={invoice.status === "paid" ? "default" : "secondary"}
                >
                  {INVOICE_STATUS_LABELS[invoice.status]}
                </Badge>
              </Row>
              <Row label="Subtotal">{money(invoice.subtotal, invoice.currency)}</Row>
              <Row label="Tax">{money(invoice.tax_total, invoice.currency)}</Row>
              <Row label="Total">
                <span className="font-medium">
                  {money(invoice.total, invoice.currency)}
                </span>
              </Row>
              <Row label="Paid">{money(invoice.amount_paid, invoice.currency)}</Row>
              <Row label="Outstanding">
                <span
                  className={cn(
                    "font-medium",
                    outstanding > 0 && "text-amber-600 dark:text-amber-400"
                  )}
                >
                  {money(outstanding, invoice.currency)}
                </span>
              </Row>
              <Row label="Due">
                {new Date(invoice.due_date).toLocaleDateString()}
              </Row>
            </CardContent>
          </Card>

          {invoice.related.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Same order</CardTitle>
                <CardDescription>
                  One-time and recurring bills reconciled side by side.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {invoice.related.map((sibling) => (
                  <Link
                    key={sibling.id}
                    to={`/app/invoices/${sibling.id}`}
                    className="flex items-center justify-between rounded-lg border p-2.5 text-sm transition-colors hover:border-foreground/25"
                  >
                    <span>
                      <span className="font-mono text-xs">{sibling.number}</span>
                      <span className="ml-2 text-muted-foreground">
                        {sibling.kind === "recurring" ? "Recurring" : "One-time"}
                      </span>
                    </span>
                    <span className="font-mono tabular-nums">
                      {money(sibling.total, sibling.currency)}
                    </span>
                  </Link>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Step({ label, done }: { label: string; done: boolean }) {
  const Icon = done ? CircleCheckIcon : CircleDashedIcon
  return (
    <div className="flex items-center gap-2">
      <Icon
        className={cn(
          "size-4",
          done ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"
        )}
      />
      <span className={cn("text-sm", !done && "text-muted-foreground")}>{label}</span>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{children}</span>
    </div>
  )
}
