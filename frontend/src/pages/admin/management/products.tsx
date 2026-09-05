import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontalIcon, PlusIcon } from "lucide-react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, errorMessage } from "@/lib/api"
import type { CatalogStats, ProductListRow } from "@/types/api"

function Kpi({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  )
}

function priceRange(row: ProductListRow) {
  if (row.price_min == null || row.price_max == null) return "—"
  const fmt = (value: number) =>
    new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: row.base_currency,
      maximumFractionDigits: 2,
    }).format(value)
  return row.price_min === row.price_max
    ? fmt(row.price_min)
    : `${fmt(row.price_min)} – ${fmt(row.price_max)}`
}

export default function ProductsTab() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const statsQuery = useQuery({
    queryKey: ["admin", "catalog-stats"],
    queryFn: async () => (await api.get<CatalogStats>("/admin/catalog/stats")).data,
  })
  const productsQuery = useQuery({
    queryKey: ["admin", "products"],
    queryFn: async () => (await api.get<ProductListRow[]>("/admin/products")).data,
  })

  const stats = statsQuery.data
  const products = productsQuery.data ?? []

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "products"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "catalog-stats"] }),
    ])
  }

  const setStatus = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "archive" | "restore" }) =>
      api.post(`/admin/products/${id}/${action}`),
    onSuccess: async (_data, variables) => {
      await refresh()
      toast.success(
        variables.action === "archive"
          ? "Archived. Reps can no longer quote it."
          : "Restored. It is sellable again."
      )
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not change the status.")),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/admin/products/${id}`),
    onSuccess: async () => {
      await refresh()
      toast.success("Product deleted.")
    },
    // A 409 means it is on a quotation; the detail says to archive instead.
    onError: (caught) => toast.error(errorMessage(caught, "Could not delete the product.")),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="font-heading text-xl font-semibold">Product catalog</h2>
          <p className="text-sm text-muted-foreground">
            Every product, variant and price list in one place.
          </p>
        </div>
        <Button asChild>
          <Link to="/app/admin/products/new">
            <PlusIcon className="size-4" />
            New Product
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Kpi
          title="Total Products"
          value={String((stats?.products_active ?? 0) + (stats?.products_archived ?? 0))}
          detail={`${stats?.products_active ?? 0} active, ${stats?.products_archived ?? 0} archived`}
        />
        <Kpi
          title="Pricelists"
          value={`${stats?.tier_count ?? 0} × ${stats?.currency_count ?? 0}`}
          detail={`${stats?.tier_count ?? 0} tiers, ${stats?.currency_count ?? 0} currencies`}
        />
        <Kpi
          title="Variants"
          value={String(stats?.sku_count ?? 0)}
          detail="SKUs across all products"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Products</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product name</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="w-24">Variants</TableHead>
                <TableHead>Price range</TableHead>
                <TableHead className="w-28">Unit</TableHead>
                <TableHead className="w-20">Tax %</TableHead>
                <TableHead className="w-28">Status</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map((product) => (
                <TableRow
                  key={product.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/app/admin/products/${product.id}`)}
                >
                  <TableCell className="font-medium">{product.name}</TableCell>
                  <TableCell>{product.category}</TableCell>
                  <TableCell>
                    {product.has_variants ? product.variant_count : "—"}
                  </TableCell>
                  <TableCell>{priceRange(product)}</TableCell>
                  <TableCell className="capitalize">
                    {product.unit}
                    {product.recurring_interval ? ` / ${product.recurring_interval}` : ""}
                  </TableCell>
                  <TableCell>{product.tax_percent}%</TableCell>
                  <TableCell>
                    <Badge
                      variant={product.status === "active" ? "secondary" : "outline"}
                      className="capitalize"
                    >
                      {product.status}
                    </Badge>
                  </TableCell>
                  <TableCell onClick={(event) => event.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label="Actions">
                          <MoreHorizontalIcon className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link to={`/app/admin/products/${product.id}`}>Edit</Link>
                        </DropdownMenuItem>
                        {product.status === "active" ? (
                          <DropdownMenuItem
                            onClick={() =>
                              setStatus.mutate({ id: product.id, action: "archive" })
                            }
                          >
                            Archive
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem
                            onClick={() =>
                              setStatus.mutate({ id: product.id, action: "restore" })
                            }
                          >
                            Restore
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem
                          variant="destructive"
                          onClick={() => remove.mutate(product.id)}
                        >
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
              {!products.length && (
                <TableRow>
                  <TableCell colSpan={8} className="text-sm text-muted-foreground">
                    No products yet.
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
