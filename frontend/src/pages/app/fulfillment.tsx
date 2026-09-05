import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { SearchIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { SortableHeader } from "@/components/sortable-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useTableSort } from "@/hooks/use-table-sort"
import {
  useFulfillmentList,
  useStock,
} from "@/features/fulfillment/use-fulfillment"
import { money, relativeTime } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import {
  FULFILLMENT_STATUS_LABELS,
  type FulfillmentStatus,
  type StockItem,
} from "@/types/api"

const STATUS_TONE: Record<
  FulfillmentStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  split_pending: "secondary",
  reserved: "outline",
  backorder: "destructive",
  partially_shipped: "secondary",
  fulfilled: "default",
  cancelled: "outline",
}

export default function FulfillmentPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState("")
  const [openOnly, setOpenOnly] = useState(true)

  const { data: stock } = useStock()
  const { data: orders, isLoading } = useFulfillmentList({
    page: 1,
    size: 50,
    openOnly,
  })

  const filteredStock = useMemo(() => {
    const rows = stock ?? []
    if (!search.trim()) return rows
    const needle = search.trim().toLowerCase()
    return rows.filter(
      (row) =>
        row.product_name.toLowerCase().includes(needle) ||
        row.sku.toLowerCase().includes(needle) ||
        row.warehouse_name.toLowerCase().includes(needle)
    )
  }, [stock, search])

  const { sorted, sortKey, direction, toggle } = useTableSort<StockItem>(
    filteredStock,
    "warehouse_name"
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Fulfillment and stock"
        description="Live stock per warehouse, plus every order that still needs fulfilling."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Live stock</CardTitle>
              <CardDescription>
                Available is what is on hand minus what is already reserved
                against an accepted split.
              </CardDescription>
            </div>
            <div className="relative min-w-[15rem]">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Product, SKU or warehouse"
                className="pl-8"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <div className="max-h-96 overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-background">
                <TableRow>
                  <SortableHeader
                    column="warehouse_name"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                  >
                    Warehouse
                  </SortableHeader>
                  <SortableHeader
                    column="product_name"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                  >
                    Product
                  </SortableHeader>
                  <SortableHeader
                    column="sku"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                    className="min-w-[16rem]"
                  >
                    SKU
                  </SortableHeader>
                  <SortableHeader
                    column="quantity_on_hand"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                    className="text-right"
                  >
                    In stock
                  </SortableHeader>
                  <SortableHeader
                    column="quantity_reserved"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                    className="text-right"
                  >
                    Reserved
                  </SortableHeader>
                  <SortableHeader
                    column="quantity_available"
                    active={sortKey}
                    direction={direction}
                    onSort={toggle}
                    className="text-right"
                  >
                    Available
                  </SortableHeader>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-muted-foreground">
                      No stock matches.
                    </TableCell>
                  </TableRow>
                ) : (
                  sorted.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-medium">
                        {row.warehouse_name}
                      </TableCell>
                      <TableCell>{row.product_name}</TableCell>
                      <TableCell className="font-mono text-xs">{row.sku}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {row.quantity_on_hand}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                        {row.quantity_reserved}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-mono tabular-nums",
                          row.quantity_available === 0 &&
                            "text-red-600 dark:text-red-400"
                        )}
                      >
                        {row.quantity_available}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Orders awaiting fulfillment</CardTitle>
              <CardDescription>
                Click an order to open its warehouse split.
              </CardDescription>
            </div>
            <Button
              variant={openOnly ? "default" : "outline"}
              size="sm"
              onClick={() => setOpenOnly((current) => !current)}
            >
              {openOnly ? "Open only" : "All orders"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          {isLoading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">Loading orders…</p>
          ) : (orders?.items ?? []).length === 0 ? (
            <p className="px-6 py-10 text-center text-sm text-muted-foreground">
              Nothing is waiting to be fulfilled.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Order</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Warehouses</TableHead>
                    <TableHead className="text-right">Shipments</TableHead>
                    <TableHead className="text-right">Est. cost</TableHead>
                    <TableHead>Confirmed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(orders?.items ?? []).map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/app/fulfillment/${row.id}`)}
                    >
                      <TableCell className="font-mono text-xs">
                        {row.quotation_number}
                      </TableCell>
                      <TableCell className="font-medium">{row.customer_name}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_TONE[row.status]}>
                          {FULFILLMENT_STATUS_LABELS[row.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.warehouse_names.join(" + ") || "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {row.estimated_shipment_count}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(row.estimated_shipping_cost, row.currency)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {relativeTime(row.created_at)}
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
