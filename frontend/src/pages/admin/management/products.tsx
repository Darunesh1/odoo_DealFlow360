import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontalIcon, PlusIcon, SearchIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { SortableHeader } from "@/components/sortable-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
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
import { api, errorMessage } from "@/lib/api"
import type {
  CatalogStats,
  Page,
  ProductListRow,
  ProductSort,
  ProductStatus,
} from "@/types/api"

const PAGE_SIZE = 10

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

export default function ProductsTab({ readOnly = false }: { readOnly?: boolean }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState("")
  const [debounced, setDebounced] = useState("")
  const [statusFilter, setStatusFilter] = useState<ProductStatus | "all">("all")
  const [sort, setSort] = useState<ProductSort>("name")
  const [order, setOrder] = useState<"asc" | "desc">("asc")
  const [page, setPage] = useState(1)

  // The same 300 ms debounce the users screen uses, so typing does not fire a
  // request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  // Any change to what is being filtered invalidates the current page number.
  useEffect(() => {
    setPage(1)
  }, [debounced, statusFilter, sort, order])

  const statsQuery = useQuery({
    queryKey: ["catalog-stats"],
    queryFn: async () => (await api.get<CatalogStats>("/catalog/stats")).data,
  })
  const productsQuery = useQuery({
    queryKey: ["products", { debounced, statusFilter, sort, order, page }],
    queryFn: async () =>
      (
        await api.get<Page<ProductListRow>>("/products", {
          params: {
            page,
            size: PAGE_SIZE,
            sort,
            order,
            ...(debounced ? { search: debounced } : {}),
            ...(statusFilter === "all" ? {} : { status: statusFilter }),
          },
        })
      ).data,
    placeholderData: keepPreviousData,
  })

  const stats = statsQuery.data
  const products = productsQuery.data?.items ?? []
  const total = productsQuery.data?.total ?? 0
  const pages = productsQuery.data?.pages ?? 0

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["products"] }),
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] }),
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

  const onSort = (column: ProductSort) => {
    if (column === sort) {
      setOrder((current) => (current === "asc" ? "desc" : "asc"))
      return
    }
    setSort(column)
    setOrder("asc")
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="font-heading text-xl font-semibold">Product catalog</h2>
          <p className="text-sm text-muted-foreground">
            Every product, variant and price list in one place.
          </p>
        </div>
        {!readOnly && (
          <Button asChild>
            <Link to="/app/admin/products/new">
              <PlusIcon className="size-4" />
              New Product
            </Link>
          </Button>
        )}
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
        <CardHeader className="gap-3">
          <CardTitle className="text-base">Products</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search name, category or SKU"
                className="pl-8"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => setStatusFilter(value as ProductStatus | "all")}
            >
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="archived">Archived</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader
                  column="name"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[14rem]"
                >
                  Product name
                </SortableHeader>
                <SortableHeader
                  column="category"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[9rem]"
                >
                  Category
                </SortableHeader>
                <SortableHeader
                  column="variants"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[7rem]"
                >
                  Variants
                </SortableHeader>
                <SortableHeader
                  column="price"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[13rem]"
                >
                  Price range
                </SortableHeader>
                <TableHead className="min-w-[8rem]">Unit</TableHead>
                <SortableHeader
                  column="tax"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[6rem]"
                >
                  Tax %
                </SortableHeader>
                <SortableHeader
                  column="status"
                  active={sort}
                  direction={order}
                  onSort={onSort}
                  className="min-w-[7rem]"
                >
                  Status
                </SortableHeader>
                {!readOnly && <TableHead className="w-16" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.map((product) => (
                <TableRow
                  key={product.id}
                  className="cursor-pointer"
                  onClick={() =>
                    navigate(
                      readOnly
                        ? `/app/products/${product.id}`
                        : `/app/admin/products/${product.id}`
                    )
                  }
                >
                  <TableCell className="font-medium">{product.name}</TableCell>
                  <TableCell>{product.category}</TableCell>
                  <TableCell>
                    {product.has_variants ? product.variant_count : "—"}
                  </TableCell>
                  <TableCell className="tabular-nums">{priceRange(product)}</TableCell>
                  <TableCell className="capitalize">
                    {product.unit}
                    {product.recurring_interval ? ` / ${product.recurring_interval}` : ""}
                  </TableCell>
                  <TableCell className="tabular-nums">{product.tax_percent}%</TableCell>
                  <TableCell>
                    <Badge
                      variant={product.status === "active" ? "secondary" : "outline"}
                      className="capitalize"
                    >
                      {product.status}
                    </Badge>
                  </TableCell>
                  {!readOnly && (
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
                  )}
                </TableRow>
              ))}
              {!products.length && (
                <TableRow>
                  <TableCell colSpan={readOnly ? 7 : 8} className="text-sm text-muted-foreground">
                    {debounced ? "No products match that search." : "No products yet."}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {total} product{total === 1 ? "" : "s"}
          {pages > 1 && ` · page ${page} of ${pages}`}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => setPage((current) => current + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
