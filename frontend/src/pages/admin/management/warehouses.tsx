import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, Trash2Icon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

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
import { api, errorMessage } from "@/lib/api"
import type { StockItem, Warehouse } from "@/types/api"

const EMPTY = {
  code: "",
  name: "",
  address: "",
  shipping_base_cost: "0",
  shipping_cost_per_unit: "0",
  shipping_cost_weight: "1",
  split_priority: "100",
}

export default function WarehousesTab() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY)

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
          shipping_base_cost: Number(form.shipping_base_cost) || 0,
          shipping_cost_per_unit: Number(form.shipping_cost_per_unit) || 0,
          shipping_cost_weight: Number(form.shipping_cost_weight) || 1,
          split_priority: Number(form.split_priority) || 100,
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
            The three cost columns are what the split planner minimises: base cost plus
            per-unit cost, scaled by weight. Priority breaks ties.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Address</TableHead>
                <TableHead className="w-28">Base cost</TableHead>
                <TableHead className="w-28">Per unit</TableHead>
                <TableHead className="w-24">Weight</TableHead>
                <TableHead className="w-24">Priority</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {warehouses.map((warehouse) => (
                <TableRow key={warehouse.id}>
                  <TableCell className="font-medium">{warehouse.code}</TableCell>
                  <TableCell>{warehouse.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {warehouse.address ?? "—"}
                  </TableCell>
                  {(
                    [
                      ["shipping_base_cost", warehouse.shipping_base_cost],
                      ["shipping_cost_per_unit", warehouse.shipping_cost_per_unit],
                      ["shipping_cost_weight", warehouse.shipping_cost_weight],
                      ["split_priority", warehouse.split_priority],
                    ] as const
                  ).map(([field, value]) => (
                    <TableCell key={field}>
                      <Input
                        type="number"
                        step="0.01"
                        className="h-8 w-24"
                        defaultValue={value}
                        onBlur={(event) => {
                          const next = Number(event.target.value)
                          if (next !== value) {
                            patch.mutate({ id: warehouse.id, body: { [field]: next } })
                          }
                        }}
                      />
                    </TableCell>
                  ))}
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
          <div className="space-y-2 md:col-span-2">
            <Label>Name</Label>
            <Input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Address</Label>
            <Input
              value={form.address}
              onChange={(event) => setForm({ ...form, address: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Shipping base cost</Label>
            <Input
              type="number"
              step="0.01"
              value={form.shipping_base_cost}
              onChange={(event) =>
                setForm({ ...form, shipping_base_cost: event.target.value })
              }
            />
          </div>
          <div className="space-y-2">
            <Label>Cost per unit</Label>
            <Input
              type="number"
              step="0.01"
              value={form.shipping_cost_per_unit}
              onChange={(event) =>
                setForm({ ...form, shipping_cost_per_unit: event.target.value })
              }
            />
          </div>
          <div className="space-y-2">
            <Label>Cost weight</Label>
            <Input
              type="number"
              step="0.01"
              value={form.shipping_cost_weight}
              onChange={(event) =>
                setForm({ ...form, shipping_cost_weight: event.target.value })
              }
            />
          </div>
          <div className="space-y-2">
            <Label>Split priority</Label>
            <Input
              type="number"
              value={form.split_priority}
              onChange={(event) => setForm({ ...form, split_priority: event.target.value })}
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
        <CardHeader>
          <CardTitle className="text-base">Stock</CardTitle>
          <CardDescription>
            Per SKU, per warehouse. Quantities are entered on the product form.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Warehouse</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="w-24 text-right">In stock</TableHead>
                <TableHead className="w-24 text-right">Reserved</TableHead>
                <TableHead className="w-24 text-right">Available</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stock.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.warehouse_name}</TableCell>
                  <TableCell>
                    {item.product_name}
                    {item.variant_name !== "Default" && (
                      <span className="text-muted-foreground"> · {item.variant_name}</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{item.sku}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.quantity_on_hand}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.quantity_reserved}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.quantity_available}
                  </TableCell>
                </TableRow>
              ))}
              {!stock.length && (
                <TableRow>
                  <TableCell colSpan={6} className="text-sm text-muted-foreground">
                    Nothing stocked yet.
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
