import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { money } from "@/features/quotations/format"
import { useMyInvoices } from "@/features/portal/use-portal"

export default function PortalInvoicesPage() {
  const { data, isLoading } = useMyInvoices()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Your account"
        title="Invoices"
        description="Everything billed to you, one-time and recurring."
      />

      <Card>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : (data ?? []).length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">
              Nothing has been billed yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Issued</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data ?? []).map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-mono text-xs">{row.number}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(row.issue_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(row.due_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {money(row.total, row.currency)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                      {money(row.amount_paid, row.currency)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={row.status === "paid" ? "default" : "secondary"}>
                        {row.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
