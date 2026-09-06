import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeftIcon, PlusIcon, Trash2Icon, WandSparklesIcon, XIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

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
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, errorMessage } from "@/lib/api"
import {
  PRODUCT_UNITS,
  RECURRING_INTERVALS,
  type Currency,
  type CustomerTier,
  type Product,
  type ProductUnit,
  type RecurringInterval,
  type VariantRowInput,
  type Warehouse,
} from "@/types/api"

/** One editable row of the matrix. Only these three fields are ever typed —
 * every tier and currency price is derived from base price. */
/** Forced by the subscription toggle; the server enforces the same rule. */
const SUBSCRIPTION_CATEGORY = "Subscription"

interface MatrixRow {
  sku: string
  unitCost: string
  basePrice: string
  /** warehouse id -> quantity, as typed. Stocked products only. */
  quantity: Record<string, string>
  /** Licences available to sell. Subscriptions only, as typed. */
  capacity: string
}

interface AttributeDraft {
  name: string
  values: string[]
  /** The value being typed, before + commits it to a chip. */
  pending: string
}

export default function ProductDetailPage({ readOnly = false }: { readOnly?: boolean }) {
  const { productId } = useParams<{ productId: string }>()
  const isNew = !productId || productId === "new"
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [name, setName] = useState("")
  const [category, setCategory] = useState("")
  const [description, setDescription] = useState("")
  const [unit, setUnit] = useState<ProductUnit>("each")
  const [taxPercent, setTaxPercent] = useState("0")
  const [isSubscription, setIsSubscription] = useState(false)
  const [interval, setInterval] = useState<RecurringInterval>("monthly")
  const [hasVariants, setHasVariants] = useState(false)
  const [attributes, setAttributes] = useState<AttributeDraft[]>([
    { name: "", values: [], pending: "" },
  ])
  const [matrix, setMatrix] = useState<Record<string, MatrixRow>>({})

  const productQuery = useQuery({
    queryKey: ["product", productId],
    queryFn: async () => (await api.get<Product>(`/products/${productId}`)).data,
    enabled: !isNew,
  })
  const tiersQuery = useQuery({
    queryKey: ["admin", "customer-tiers"],
    queryFn: async () => (await api.get<CustomerTier[]>("/admin/customer-tiers")).data,
    enabled: !readOnly,
  })
  const currenciesQuery = useQuery({
    queryKey: ["admin", "currencies"],
    queryFn: async () => (await api.get<Currency[]>("/admin/currencies")).data,
    enabled: !readOnly,
  })
  const warehousesQuery = useQuery({
    queryKey: ["admin", "warehouses"],
    queryFn: async () => (await api.get<Warehouse[]>("/admin/warehouses")).data,
    enabled: !readOnly,
  })
  const categoriesQuery = useQuery({
    queryKey: ["categories"],
    queryFn: async () => (await api.get<string[]>("/categories")).data,
  })

  const product = productQuery.data ?? null
  const tiers = tiersQuery.data ?? []
  const currencies = currenciesQuery.data ?? []
  const warehouses = useMemo(
    () => (warehousesQuery.data ?? []).filter((warehouse) => warehouse.is_active),
    [warehousesQuery.data]
  )
  const categories = categoriesQuery.data ?? []
  const baseCurrency = currencies.find((item) => item.is_base) ?? currencies[0] ?? null

  useEffect(() => {
    if (!product) return
    setName(product.name)
    setCategory(product.category)
    setDescription(product.description ?? "")
    setUnit(product.unit)
    setTaxPercent(String(product.tax_percent))
    setIsSubscription(product.is_subscription)
    if (product.recurring_interval) setInterval(product.recurring_interval)
    setHasVariants(product.has_variants)
    setAttributes(
      product.attributes.length
        ? product.attributes.map((attribute) => ({
            name: attribute.name,
            values: attribute.values.map((value) => value.value),
            pending: "",
          }))
        : [{ name: "", values: [], pending: "" }]
    )
    const next: Record<string, MatrixRow> = {}
    for (const variant of product.variants) {
      const quantity: Record<string, string> = {}
      for (const item of variant.stock) {
        quantity[item.warehouse_id] = String(item.quantity_on_hand)
      }
      next[variant.id] = {
        sku: variant.sku,
        unitCost: variant.unit_cost ? String(variant.unit_cost) : "",
        basePrice: variant.base_price ? String(variant.base_price) : "",
        quantity,
        capacity:
          variant.available_quantity !== null &&
          variant.available_quantity !== undefined
            ? String(variant.available_quantity)
            : "",
      }
    }
    setMatrix(next)
  }, [product])

  const variants = product?.variants ?? []
  const stocked = !isSubscription

  /** The formula, mirrored client-side so the grid fills as you type. The
   * server recomputes it on save; this is preview, not the source of truth.
   *
   * The tier no longer discounts the price - it caps what a rep may take off.
   * So every tier sees the same list, and what differs is the floor. */
  const listPrice = (basePrice: string, currency: Currency) => {
    const amount = Number(basePrice)
    if (!basePrice || !Number.isFinite(amount) || !baseCurrency) return null
    return (amount * baseCurrency.rate_to_base) / currency.rate_to_base
  }

  /** The lowest a rep on this tier may sell it for. */
  const floorPrice = (basePrice: string, tier: CustomerTier, currency: Currency) => {
    const list = listPrice(basePrice, currency)
    return list == null ? null : list * (1 - tier.max_discount_percent / 100)
  }

  const rowComplete = (row: MatrixRow | undefined) =>
    Boolean(row) &&
    Number(row!.unitCost) > 0 &&
    Number(row!.basePrice) > 0 &&
    // A plan is capped, everything else is stocked. Both are required; a SKU
    // with neither would reach the rep's picker as sellable without end.
    (stocked
      ? warehouses.every(
          (w) =>
            row!.quantity[w.id]?.trim() !== undefined &&
            row!.quantity[w.id]?.trim() !== ""
        )
      : Number(row!.capacity) > 0)

  const matrixComplete =
    variants.length > 0 && variants.every((variant) => rowComplete(matrix[variant.id]))

  const attributesReady =
    attributes.length > 0 &&
    attributes.every((attribute) => attribute.name.trim() && attribute.values.length > 0)

  const generalInfo = () => ({
    name: name.trim(),
    category: category.trim(),
    description: description || null,
    unit,
    tax_percent: Number(taxPercent) || 0,
    is_subscription: isSubscription,
    recurring_interval: isSubscription ? interval : null,
    has_variants: hasVariants,
    attributes: hasVariants
      ? attributes
          .filter((attribute) => attribute.name.trim() && attribute.values.length)
          .map((attribute) => ({
            name: attribute.name.trim(),
            values: attribute.values,
          }))
      : [],
  })

  const saveGeneral = useMutation({
    mutationFn: async () => {
      if (isNew) {
        return (await api.post<Product>("/admin/products", generalInfo())).data
      }
      return (await api.patch<Product>(`/admin/products/${productId}`, generalInfo())).data
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["products"] })
      await queryClient.invalidateQueries({ queryKey: ["catalog-stats"] })
      await queryClient.invalidateQueries({ queryKey: ["categories"] })
      if (isNew) {
        navigate(`/app/admin/products/${saved.id}`, { replace: true })
        toast.success("Product created. Now set its cost, price and stock.")
        return
      }
      queryClient.setQueryData(["product", productId], saved)
      toast.success("Product saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the product.")),
  })

  const generate = useMutation({
    mutationFn: async () =>
      (await api.post<Product>(`/admin/products/${productId}/generate-variants`)).data,
    onSuccess: async (saved) => {
      queryClient.setQueryData(["product", productId], saved)
      await queryClient.invalidateQueries({ queryKey: ["catalog-stats"] })
      toast.success(`${saved.variants.length} variant(s) ready.`)
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not generate variants.")),
  })

  const saveMatrix = useMutation({
    mutationFn: async () => {
      const rows: VariantRowInput[] = variants.map((variant) => {
        const row = matrix[variant.id]
        return {
          id: variant.id,
          sku: row?.sku ?? variant.sku,
          unit_cost: Number(row?.unitCost ?? 0),
          base_price: Number(row?.basePrice ?? 0),
          available_quantity: stocked ? null : Number(row?.capacity ?? 0) || 0,
          stock: stocked
            ? warehouses.map((warehouse) => ({
                warehouse_id: warehouse.id,
                quantity_on_hand: Number(row?.quantity[warehouse.id] ?? 0) || 0,
              }))
            : [],
        }
      })
      return (await api.put<Product>(`/admin/products/${productId}/variants`, { rows })).data
    },
    onSuccess: async (saved) => {
      queryClient.setQueryData(["product", productId], saved)
      await queryClient.invalidateQueries({ queryKey: ["products"] })
      await queryClient.invalidateQueries({ queryKey: ["admin", "price-matrix"] })
      toast.success("Cost, price and stock saved. Tier prices recalculated.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the matrix.")),
  })

  const addValue = (index: number) => {
    setAttributes((current) =>
      current.map((attribute, position) => {
        if (position !== index) return attribute
        const value = attribute.pending.trim()
        if (!value || attribute.values.includes(value)) {
          return { ...attribute, pending: "" }
        }
        return { ...attribute, values: [...attribute.values, value], pending: "" }
      })
    )
  }

  const patchRow = (variantId: string, patch: Partial<MatrixRow>) =>
    setMatrix((current) => ({
      ...current,
      [variantId]: { ...current[variantId], ...patch },
    }))

  if (readOnly) {
    return <ReadOnlyProduct product={product} />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/app/admin/products">
            <ArrowLeftIcon className="size-4" />
            Product catalog
          </Link>
        </Button>
        <Button
          onClick={() => saveGeneral.mutate()}
          disabled={!name.trim() || !category.trim() || saveGeneral.isPending}
        >
          {isNew ? "Create product" : "Save product"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">General Info</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Product name</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Category</Label>
            <Input
              list="known-categories"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="Hardware"
              // The toggle is the only place subscription-ness is declared, so
              // the category follows it rather than being typed alongside it
              // and allowed to disagree.
              readOnly={isSubscription}
              disabled={isSubscription}
            />
            {isSubscription ? (
              <p className="text-xs text-muted-foreground">
                Set by the subscription toggle.
              </p>
            ) : null}
            {/* Suggests names already in use, but accepts anything typed.
                "Subscription" is never among them - the server refuses it on a
                product whose toggle is off. */}
            <datalist id="known-categories">
              {categories.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </div>
          <div className="space-y-2">
            <Label>Unit</Label>
            <Select value={unit} onValueChange={(value) => setUnit(value as ProductUnit)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRODUCT_UNITS.map((item) => (
                  <SelectItem key={item} value={item} className="capitalize">
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Description</Label>
            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Tax %</Label>
            <Input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={taxPercent}
              onChange={(event) => setTaxPercent(event.target.value)}
            />
          </div>

          <div className="flex items-center gap-3">
            <Switch
              id="is-subscription"
              checked={isSubscription}
              onCheckedChange={(next) => {
                setIsSubscription(next)
                // Mirrors the server rule immediately, so the form never shows
                // a state the API would reject.
                if (next) setCategory(SUBSCRIPTION_CATEGORY)
                else if (category === SUBSCRIPTION_CATEGORY) setCategory("")
              }}
            />
            <Label htmlFor="is-subscription">Subscription</Label>
          </div>
          {/* Recurring only exists when subscription is yes; the database
              enforces the same pairing. */}
          {isSubscription && (
            <div className="space-y-2">
              <Label>Recurring</Label>
              <Select
                value={interval}
                onValueChange={(value) => setInterval(value as RecurringInterval)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RECURRING_INTERVALS.map((item) => (
                    <SelectItem key={item} value={item} className="capitalize">
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex items-center gap-3">
            <Switch id="has-variants" checked={hasVariants} onCheckedChange={setHasVariants} />
            <Label htmlFor="has-variants">Has variants</Label>
          </div>
        </CardContent>
      </Card>

      {hasVariants && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Product Variants</CardTitle>
            <CardDescription>
              Name an attribute, then add its values one at a time. Generating builds
              every combination and leaves the ones you have already priced untouched.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[14rem]">Attribute</TableHead>
                  <TableHead className="min-w-[22rem]">Values</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {attributes.map((attribute, index) => (
                  <TableRow key={index}>
                    <TableCell className="align-top">
                      <Input
                        value={attribute.name}
                        placeholder="Color"
                        onChange={(event) =>
                          setAttributes((current) =>
                            current.map((item, position) =>
                              position === index
                                ? { ...item, name: event.target.value }
                                : item
                            )
                          )
                        }
                      />
                    </TableCell>
                    <TableCell className="space-y-2 align-top">
                      {attribute.values.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {attribute.values.map((value) => (
                            <Badge key={value} variant="secondary" className="gap-1 pr-1">
                              {value}
                              <button
                                type="button"
                                aria-label={`Remove ${value}`}
                                className="rounded-full p-0.5 hover:bg-muted-foreground/20"
                                onClick={() =>
                                  setAttributes((current) =>
                                    current.map((item, position) =>
                                      position === index
                                        ? {
                                            ...item,
                                            values: item.values.filter(
                                              (entry) => entry !== value
                                            ),
                                          }
                                        : item
                                    )
                                  )
                                }
                              >
                                <XIcon className="size-3" />
                              </button>
                            </Badge>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-2">
                        <Input
                          value={attribute.pending}
                          placeholder="Add a value"
                          onChange={(event) =>
                            setAttributes((current) =>
                              current.map((item, position) =>
                                position === index
                                  ? { ...item, pending: event.target.value }
                                  : item
                              )
                            )
                          }
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault()
                              addValue(index)
                            }
                          }}
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          size="icon"
                          aria-label="Add value"
                          disabled={!attribute.pending.trim()}
                          onClick={() => addValue(index)}
                        >
                          <PlusIcon className="size-4" />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remove attribute"
                        onClick={() =>
                          setAttributes((current) =>
                            current.filter((_, position) => position !== index)
                          )
                        }
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                onClick={() =>
                  setAttributes((current) => [
                    ...current,
                    { name: "", values: [], pending: "" },
                  ])
                }
              >
                <PlusIcon className="size-4" />
                Add attribute
              </Button>
              <Button
                variant="secondary"
                // Nothing to generate until every attribute has a name and at
                // least one value.
                disabled={isNew || !attributesReady || generate.isPending}
                onClick={async () => {
                  await saveGeneral.mutateAsync()
                  generate.mutate()
                }}
              >
                <WandSparklesIcon className="size-4" />
                Generate variants
              </Button>
              {!attributesReady && (
                <span className="text-xs text-muted-foreground">
                  Give every attribute a name and at least one value.
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {!isNew && variants.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {hasVariants ? "Variants, stock and pricing" : "Pricing and stock"}
            </CardTitle>
            <CardDescription>
              Enter the unit cost and the unit price in{" "}
              {baseCurrency?.code ?? "the base currency"}. Every tier and currency price
              is calculated from the price and that tier&apos;s discount — margin comes
              from the cost.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {hasVariants && <TableHead className="min-w-[12rem]">Variant</TableHead>}
                  <TableHead className="min-w-[16rem]">SKU</TableHead>
                  <TableHead className="min-w-[9rem]">
                    Unit cost ({baseCurrency?.code})
                  </TableHead>
                  <TableHead className="min-w-[9rem]">
                    Unit price ({baseCurrency?.code})
                  </TableHead>
                  {/* A plan is capped, not stocked: one licence figure in
                      place of a column per warehouse, because a subscription
                      does not sit in a depot. */}
                  {stocked ? (
                    warehouses.map((warehouse) => (
                      <TableHead key={warehouse.id} className="min-w-[7rem]">
                        {warehouse.name}
                      </TableHead>
                    ))
                  ) : (
                    <TableHead className="min-w-[10rem]">
                      Available licences
                    </TableHead>
                  )}
                  {tiers.flatMap((tier) =>
                    currencies.map((currency) => (
                      <TableHead
                        key={`${tier.id}-${currency.code}`}
                        className="min-w-[8rem] text-right"
                      >
                        {tier.name} {currency.code}
                        <span className="block text-[11px] font-normal text-muted-foreground">
                          list · floor at {tier.max_discount_percent}%
                        </span>
                      </TableHead>
                    ))
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {variants.map((variant) => {
                  const row = matrix[variant.id]
                  return (
                    <TableRow key={variant.id}>
                      {hasVariants && (
                        <TableCell className="font-medium">{variant.name}</TableCell>
                      )}
                      <TableCell>
                        <Input
                          value={row?.sku ?? variant.sku}
                          className="h-8 font-mono text-xs"
                          onChange={(event) =>
                            patchRow(variant.id, { sku: event.target.value })
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          className="h-8"
                          placeholder="required"
                          aria-invalid={!row?.unitCost || Number(row.unitCost) <= 0}
                          value={row?.unitCost ?? ""}
                          onChange={(event) =>
                            patchRow(variant.id, { unitCost: event.target.value })
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          className="h-8"
                          placeholder="required"
                          aria-invalid={!row?.basePrice || Number(row.basePrice) <= 0}
                          value={row?.basePrice ?? ""}
                          onChange={(event) =>
                            patchRow(variant.id, { basePrice: event.target.value })
                          }
                        />
                      </TableCell>
                      {stocked ? (
                        warehouses.map((warehouse) => (
                          <TableCell key={warehouse.id}>
                            <Input
                              type="number"
                              min="0"
                              className="h-8"
                              placeholder="required"
                              aria-invalid={
                                (row?.quantity[warehouse.id] ?? "").trim() === ""
                              }
                              value={row?.quantity[warehouse.id] ?? ""}
                              onChange={(event) =>
                                patchRow(variant.id, {
                                  quantity: {
                                    ...(row?.quantity ?? {}),
                                    [warehouse.id]: event.target.value,
                                  },
                                })
                              }
                            />
                          </TableCell>
                        ))
                      ) : (
                        <TableCell>
                          <Input
                            type="number"
                            min="1"
                            className="h-8"
                            placeholder="required"
                            aria-invalid={!row?.capacity || Number(row.capacity) <= 0}
                            value={row?.capacity ?? ""}
                            onChange={(event) =>
                              patchRow(variant.id, { capacity: event.target.value })
                            }
                          />
                        </TableCell>
                      )}
                      {tiers.flatMap((tier) =>
                        currencies.map((currency) => {
                          const list = listPrice(row?.basePrice ?? "", currency)
                          const floor = floorPrice(row?.basePrice ?? "", tier, currency)
                          return (
                            <TableCell
                              key={`${tier.id}-${currency.code}`}
                              className="text-right tabular-nums"
                            >
                              {list == null ? (
                                "—"
                              ) : (
                                <>
                                  <span className="block">{list.toFixed(2)}</span>
                                  <span className="block text-xs text-muted-foreground">
                                    floor {floor!.toFixed(2)}
                                  </span>
                                </>
                              )}
                            </TableCell>
                          )
                        })
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={() => saveMatrix.mutate()}
                disabled={!matrixComplete || saveMatrix.isPending}
              >
                Save prices and stock
              </Button>
              {!matrixComplete && (
                <span className="text-xs text-muted-foreground">
                  Every SKU needs a unit cost, a unit price and
                  {stocked
                    ? " a quantity for each warehouse"
                    : " the number of licences available"}
                  .
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/** What a sales rep, manager or finance user sees: the same product, no inputs. */
function ReadOnlyProduct({ product }: { product: Product | null }) {
  if (!product) return null
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/app/products">
          <ArrowLeftIcon className="size-4" />
          Product catalog
        </Link>
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{product.name}</CardTitle>
          <CardDescription>
            {product.category} · {product.unit}
            {product.recurring_interval ? ` / ${product.recurring_interval}` : ""} ·{" "}
            {product.tax_percent}% tax
          </CardDescription>
        </CardHeader>
        {product.description && (
          <CardContent className="text-sm text-muted-foreground">
            {product.description}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Variants and prices</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[12rem]">Variant</TableHead>
                <TableHead className="min-w-[16rem]">SKU</TableHead>
                <TableHead className="min-w-[10rem]">Available</TableHead>
                <TableHead className="min-w-[16rem]">Prices</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {product.variants.map((variant) => (
                <TableRow key={variant.id}>
                  <TableCell className="font-medium">{variant.name}</TableCell>
                  <TableCell className="font-mono text-xs">{variant.sku}</TableCell>
                  <TableCell className="tabular-nums">
                    {variant.stock.reduce((sum, item) => sum + item.quantity_available, 0)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {variant.prices
                      .map((price) => `${price.unit_price.toFixed(2)} ${price.currency_code}`)
                      .join(" · ") || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
