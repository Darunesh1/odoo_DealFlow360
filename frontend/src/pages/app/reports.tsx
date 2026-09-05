import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { DownloadIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
import {
  downloadReport,
  useReport,
  type ReportFilters,
} from "@/features/analytics/use-analytics"
import { money } from "@/features/quotations/format"
import { api } from "@/lib/api"

const ALL = "__all__"

export default function ReportsPage() {
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [category, setCategory] = useState(ALL)

  const filters: ReportFilters = useMemo(
    () => ({
      from: from || undefined,
      to: to || undefined,
      category: category === ALL ? undefined : category,
    }),
    [from, to, category]
  )

  const { data, isLoading } = useReport(filters)
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: async () => (await api.get<string[]>("/categories")).data,
    staleTime: 300_000,
  })

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Reporting"
        title="Sales reporting"
        description="Every figure comes from confirmed sales history, so last quarter's numbers never move."
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadReport("xlsx", filters)}
            >
              <DownloadIcon /> XLS
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadReport("pdf", filters)}
            >
              <DownloadIcon /> PDF
            </Button>
          </div>
        }
      />

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label>From</Label>
            <Input
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>To</Label>
            <Input
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All categories</SelectItem>
                {(categories ?? []).map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {isLoading || !data ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Figure
              label="Quotes created"
              value={String(data.quotes_created)}
              hint={`${data.quotes_confirmed} confirmed · ${data.conversion_rate}%`}
            />
            <Figure
              label="Revenue"
              value={money(data.revenue)}
              hint={`${data.units_sold} units across ${data.orders} orders`}
            />
            <Figure
              label="Margin"
              value={money(data.margin)}
              hint={`avg discount ${data.average_discount}%`}
            />
            <Figure
              label="Avg approval time"
              value={
                data.average_approval_hours !== null
                  ? `${data.average_approval_hours} h`
                  : "—"
              }
              hint={
                data.top_upsold.length > 0
                  ? `Top upsold: ${data.top_upsold[0].name}`
                  : "No upsells yet"
              }
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <FigureTable
              title="Best selling"
              description="By revenue, from confirmed sales."
              columns={["Product", "Units", "Revenue"]}
              rows={data.best_selling.map((row) => [
                row.name,
                String(row.units),
                money(row.revenue),
              ])}
            />
            <FigureTable
              title="Top upsold"
              description="Lines a rep added from the suggestion panel."
              columns={["Product", "Units", "Revenue"]}
              rows={data.top_upsold.map((row) => [
                row.name,
                String(row.units),
                money(row.revenue),
              ])}
            />
            <FigureTable
              title="Most discounted"
              description="Where the margin is going."
              columns={["Product", "Avg discount", "Lines"]}
              rows={data.most_discounted.map((row) => [
                row.name,
                `${row.average_discount}%`,
                String(row.lines),
              ])}
            />
            <FigureTable
              title="By rep"
              description="Revenue, margin and the average discount each gives."
              columns={["Rep", "Revenue", "Avg discount"]}
              rows={data.by_rep.map((row) => [
                row.name,
                money(row.revenue),
                `${row.average_discount}%`,
              ])}
            />
            <FigureTable
              title="By category"
              description="Where the revenue and the margin come from."
              columns={["Category", "Revenue", "Margin"]}
              rows={data.by_category.map((row) => [
                row.name,
                money(row.revenue),
                money(row.margin),
              ])}
            />
          </div>
        </>
      )}
    </div>
  )
}

function Figure({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="label-mono text-muted-foreground">{label}</p>
        <p className="font-mono text-2xl tabular-nums">{value}</p>
        <p className="truncate text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function FigureTable({
  title,
  description,
  columns,
  rows,
}: {
  title: string
  description: string
  columns: string[]
  rows: string[][]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((column, index) => (
                <TableHead key={column} className={index > 0 ? "text-right" : ""}>
                  {column}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-muted-foreground">
                  Nothing in this period.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row[0]}>
                  {row.map((cell, index) => (
                    <TableCell
                      key={index}
                      className={
                        index > 0 ? "text-right font-mono tabular-nums" : "font-medium"
                      }
                    >
                      {cell}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
