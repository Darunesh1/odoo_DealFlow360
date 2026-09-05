import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, SearchIcon, Trash2Icon } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { SortableHeader } from "@/components/sortable-header"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useTableSort } from "@/hooks/use-table-sort"
import { api, errorMessage } from "@/lib/api"
import type { StockItem, Warehouse } from "@/types/api"

const EMPTY = { code: "", name: "", address: "" }

export default function WarehousesTab() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY)
  const [stockSearch, setStockSearch] = useState("")

  const warehousesQuery = useQuery({
    queryKey: ["admin", "warehouses"],
    queryFn: async () => (await api.get<Warehouse[]>("/admin/warehouses")).data,
  })
  const stockQuery = useQuery({
    queryKey: ["admin", "stock"],
    queryFn: async () => (await api.get<StockItem[]>("/admin/stock")).data,
  })

  const warehouses = warehousesQuery.data ?? []
  const stock = stockQuery.data ?? []

  const warehouseSort = useTableSort(warehouses, "name")
  const filteredStock = useMemo(() => {
    const term = stockSearch.trim().toLowerCase()
    if (!term) return stock
    return stock.filter(
      (item) =>
        item.product_name.toLowerCase().includes(term) ||
        item.sku.toLowerCase().includes(term) ||
        item.warehouse_name.toLowerCase().includes(term)
    )
  }, [stock, stockSearch])
  const stockSort = useTableSort(filteredStock, "warehouse_name")

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "warehouses"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "stock"] }),
    ])
  }

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<Warehouse>("/admin/warehouses", {
          code: form.code.trim().toUpperCase(),
          name: form.name.trim(),
          address: form.address || null,
        })
      ).data,
    onSuccess: async () => {
      setForm(EMPTY)
      await refresh()
      toast.success("Warehouse created.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not create the warehouse.")),
  })

  const patch = useMutation({
    mutationFn: async ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      (await api.patch<Warehouse>(`/admin/warehouses/${id}`, body)).data,
    onSuccess: async () => {
      await refresh()
      toast.success("Warehouse saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the warehouse.")),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/admin/warehouses/${id}`),
    onSuccess: async () => {
      await refresh()
      toast.success("Warehouse deleted.")
    },
    // A 409 means it still holds stock or backs a quoted line.
    onError: (caught) => toast.error(errorMessage(caught, "Could not delete the warehouse.")),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Warehouses</CardTitle>
          <CardDescription>
            Where stock sits. Quantities are entered per SKU on the product form.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader
                  column="code"
                  active={warehouseSort.sortKey}
                  direction={warehouseSort.direction}
                  onSort={warehouseSort.toggle}
                  className="min-w-[7rem]"
                >
                  Code
                </SortableHeader>
                <SortableHeader
                  column="name"
                  active={warehouseSort.sortKey}
                  direction={warehouseSort.direction}
                  onSort={warehouseSort.toggle}
                  className="min-w-[16rem]"
                >
                  Name
                </SortableHeader>
                <TableHead className="min-w-[18rem]">Address</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {warehouseSort.sorted.map((warehouse) => (
                <TableRow key={warehouse.id}>
                  <TableCell className="font-medium">{warehouse.code}</TableCell>
                  <TableCell>
                    <Input
                      className="h-8"
                      defaultValue={warehouse.name}
                      onBlur={(event) => {
                        const next = event.target.value.trim()
                        if (next && next !== warehouse.name) {
                          patch.mutate({ id: warehouse.id, body: { name: next } })
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      className="h-8"
                      defaultValue={warehouse.address ?? ""}
                      onBlur={(event) => {
                        const next = event.target.value
                        if (next !== (warehouse.address ?? "")) {
                          patch.mutate({ id: warehouse.id, body: { address: next || null } })
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${warehouse.name}`}
                      onClick={() => remove.mutate(warehouse.id)}
                    >
                      <Trash2Icon className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!warehouses.length && (
                <TableRow>
                  <TableCell colSpan={4} className="text-sm text-muted-foreground">
                    No warehouses yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New warehouse</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="space-y-2">
            <Label>Code</Label>
            <Input
              maxLength={16}
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Address</Label>
            <Input
              value={form.address}
              onChange={(event) => setForm({ ...form, address: event.target.value })}
            />
          </div>
          <div className="md:col-span-4">
            <Button
              onClick={() => create.mutate()}
              disabled={!form.code.trim() || !form.name.trim() || create.isPending}
            >
              <PlusIcon className="size-4" />
              Create warehouse
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-3">
          <div>
            <CardTitle className="text-base">Stock</CardTitle>
            <CardDescription>Per SKU, per warehouse.</CardDescription>
          </div>
          <div className="relative max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={stockSearch}
              onChange={(event) => setStockSearch(event.target.value)}
              placeholder="Search product, SKU or warehouse"
              className="pl-8"
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader
                  column="warehouse_name"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[12rem]"
                >
                  Warehouse
                </SortableHeader>
                <SortableHeader
                  column="product_name"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[16rem]"
                >
                  Product
                </SortableHeader>
                <SortableHeader
                  column="sku"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[16rem]"
                >
                  SKU
                </SortableHeader>
                <SortableHeader
                  column="quantity_on_hand"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[7rem]"
                >
                  In stock
                </SortableHeader>
                <SortableHeader
                  column="quantity_reserved"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[7rem]"
                >
                  Reserved
                </SortableHeader>
                <SortableHeader
                  column="quantity_available"
                  active={stockSort.sortKey}
                  direction={stockSort.direction}
                  onSort={stockSort.toggle}
                  className="min-w-[7rem]"
                >
                  Available
                </SortableHeader>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stockSort.sorted.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.warehouse_name}</TableCell>
                  <TableCell>
                    {item.product_name}
                    {item.variant_name !== "Default" && (
                      <span className="text-muted-foreground"> · {item.variant_name}</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{item.sku}</TableCell>
                  <TableCell className="tabular-nums">{item.quantity_on_hand}</TableCell>
                  <TableCell className="tabular-nums">{item.quantity_reserved}</TableCell>
                  <TableCell className="tabular-nums">{item.quantity_available}</TableCell>
                </TableRow>
              ))}
              {!filteredStock.length && (
                <TableRow>
                  <TableCell colSpan={6} className="text-sm text-muted-foreground">
                    {stockSearch ? "Nothing matches that search." : "Nothing stocked yet."}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
