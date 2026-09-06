import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, SearchIcon, Trash2Icon } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

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

/** How many rows to paint at once. The browser, not the query, is the limit. */
const ROW_LIMIT = 250
import { api, errorMessage } from "@/lib/api"
import type { Currency, PriceMatrixRow } from "@/types/api"

export default function PriceListsTab() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [code, setCode] = useState("")
  const [currencyName, setCurrencyName] = useState("")
  const [rate, setRate] = useState("")

  const currenciesQuery = useQuery({
    queryKey: ["admin", "currencies"],
    queryFn: async () => (await api.get<Currency[]>("/admin/currencies")).data,
  })
  const matrixQuery = useQuery({
    queryKey: ["admin", "price-matrix"],
    queryFn: async () => (await api.get<PriceMatrixRow[]>("/admin/price-matrix")).data,
  })

  const currencies = currenciesQuery.data ?? []
  const matrix = matrixQuery.data ?? []

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return matrix
    return matrix.filter(
      (row) =>
        row.product_name.toLowerCase().includes(term) ||
        row.sku.toLowerCase().includes(term) ||
        row.tier_name.toLowerCase().includes(term)
    )
  }, [matrix, search])

  const sort = useTableSort(filtered, "product_name")
  // Every price cell for every SKU is a few thousand rows at a real catalogue
  // size, and the browser is the bottleneck, not the query. Rendering a
  // window of them keeps the page responsive; the search narrows to what you
  // are actually looking for.
  const visible = sort.sorted.slice(0, ROW_LIMIT)
  const currencySort = useTableSort(currencies, "code")

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "currencies"] }),
      queryClient.invalidateQueries({ queryKey: ["admin", "price-matrix"] }),
    ])
  }

  const createCurrency = useMutation({
    mutationFn: async () =>
      (
        await api.post<Currency>("/admin/currencies", {
          code: code.trim().toUpperCase(),
          name: currencyName.trim(),
          rate_to_base: Number(rate) || 1,
        })
      ).data,
    onSuccess: async () => {
      setCode("")
      setCurrencyName("")
      setRate("")
      await refresh()
      toast.success("Currency added.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not add the currency.")),
  })

  const updateRate = useMutation({
    mutationFn: async ({ target, value }: { target: string; value: number }) =>
      (
        await api.patch<Currency>(`/admin/currencies/${target}`, {
          rate_to_base: value,
        })
      ).data,
    onSuccess: async () => {
      await refresh()
      toast.success("Rate saved. Prices in that currency recalculated.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the rate.")),
  })

  const removeCurrency = useMutation({
    mutationFn: async (target: string) => api.delete(`/admin/currencies/${target}`),
    onSuccess: async () => {
      await refresh()
      toast.success("Currency removed.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not remove the currency.")),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Currencies</CardTitle>
          <CardDescription>
            One unit of each currency, expressed in the base currency. Changing a rate
            re-derives the prices that were converted, and leaves the ones typed by hand
            alone.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader
                  column="code"
                  active={currencySort.sortKey}
                  direction={currencySort.direction}
                  onSort={currencySort.toggle}
                  className="min-w-[8rem]"
                >
                  Code
                </SortableHeader>
                <SortableHeader
                  column="name"
                  active={currencySort.sortKey}
                  direction={currencySort.direction}
                  onSort={currencySort.toggle}
                  className="min-w-[14rem]"
                >
                  Name
                </SortableHeader>
                <TableHead className="min-w-[11rem]">Rate to base</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {currencySort.sorted.map((currency) => (
                <TableRow key={currency.code}>
                  <TableCell className="font-medium">
                    {currency.code}
                    {currency.is_base && (
                      <Badge variant="secondary" className="ml-2">
                        base
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{currency.name}</TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min="0"
                      step="0.000001"
                      className="h-8 w-32"
                      // The base rate is 1 by definition, so it is not editable.
                      disabled={currency.is_base}
                      defaultValue={currency.rate_to_base}
                      onBlur={(event) => {
                        const value = Number(event.target.value)
                        if (value && value !== currency.rate_to_base) {
                          updateRate.mutate({ target: currency.code, value })
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    {!currency.is_base && (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${currency.code}`}
                        onClick={() => removeCurrency.mutate(currency.code)}
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex flex-wrap items-end gap-2">
            <Input
              placeholder="EUR"
              maxLength={3}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="w-24"
            />
            <Input
              placeholder="Euro"
              value={currencyName}
              onChange={(event) => setCurrencyName(event.target.value)}
              className="w-44"
            />
            <Input
              type="number"
              min="0"
              step="0.000001"
              placeholder="Rate to base"
              value={rate}
              onChange={(event) => setRate(event.target.value)}
              className="w-36"
            />
            <Button
              onClick={() => createCurrency.mutate()}
              disabled={code.trim().length !== 3 || !currencyName.trim() || !rate}
            >
              <PlusIcon className="size-4" />
              Add currency
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-3">
          <div>
            <CardTitle className="text-base">Price matrix</CardTitle>
            <CardDescription>
              Every SKU at every tier and currency. Read only, and calculated: the unit
              price on the product, converted. The tier does not change it - it
              caps how far a rep may discount, which is the floor column.
            </CardDescription>
          </div>
          <div className="relative max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Filter by product, SKU or tier"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-8"
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader
                  column="product_name"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[14rem]"
                >
                  Product
                </SortableHeader>
                <SortableHeader
                  column="variant_name"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[11rem]"
                >
                  Variant
                </SortableHeader>
                <SortableHeader
                  column="sku"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[16rem]"
                >
                  SKU
                </SortableHeader>
                <SortableHeader
                  column="tier_name"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[9rem]"
                >
                  Tier
                </SortableHeader>
                <SortableHeader
                  column="currency_code"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[8rem]"
                >
                  Currency
                </SortableHeader>
                <SortableHeader
                  column="unit_price"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[9rem]"
                >
                  List price
                </SortableHeader>
                <TableHead className="min-w-[7rem] text-right">Max off</TableHead>
                <SortableHeader
                  column="floor_price"
                  active={sort.sortKey}
                  direction={sort.direction}
                  onSort={sort.toggle}
                  className="min-w-[9rem]"
                >
                  Floor
                </SortableHeader>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((row) => (
                <TableRow key={`${row.variant_id}-${row.tier_name}-${row.currency_code}`}>
                  <TableCell className="font-medium">{row.product_name}</TableCell>
                  <TableCell>{row.variant_name}</TableCell>
                  <TableCell className="font-mono text-xs">{row.sku}</TableCell>
                  <TableCell>{row.tier_name}</TableCell>
                  <TableCell>{row.currency_code}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.unit_price.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {row.max_discount_percent}%
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {row.floor_price.toFixed(2)}
                  </TableCell>
                </TableRow>
              ))}
              {sort.sorted.length > visible.length && (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="text-center text-sm text-muted-foreground"
                  >
                    Showing {visible.length} of {sort.sorted.length} rows. Search
                    to narrow it down.
                  </TableCell>
                </TableRow>
              )}
              {!filtered.length && (
                <TableRow>
                  <TableCell colSpan={8} className="text-sm text-muted-foreground">
                    No prices match.
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
