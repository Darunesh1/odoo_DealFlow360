import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeftIcon, PlusIcon, Trash2Icon, WandSparklesIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
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

/** One editable row of the matrix, keyed by variant id. */
interface MatrixRow {
  sku: string
  unitCost: string
  /** warehouse id -> quantity */
  quantity: Record<string, string>
  /** `${tierId}:${currencyCode}` -> price, as typed */
  price: Record<string, string>
  /** Which currency the admin typed for each tier; the rest are derived. */
  entered: Record<string, string>
}

const priceKey = (tierId: string, code: string) => `${tierId}:${code}`

export default function ProductDetailPage() {
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
  const [attributes, setAttributes] = useState<{ name: string; values: string }[]>([
    { name: "", values: "" },
  ])
  const [matrix, setMatrix] = useState<Record<string, MatrixRow>>({})

  const productQuery = useQuery({
    queryKey: ["admin", "product", productId],
    queryFn: async () => (await api.get<Product>(`/admin/products/${productId}`)).data,
    enabled: !isNew,
  })
  const tiersQuery = useQuery({
    queryKey: ["admin", "customer-tiers"],
    queryFn: async () => (await api.get<CustomerTier[]>("/admin/customer-tiers")).data,
  })
  const currenciesQuery = useQuery({
    queryKey: ["admin", "currencies"],
    queryFn: async () => (await api.get<Currency[]>("/admin/currencies")).data,
  })
  const warehousesQuery = useQuery({
    queryKey: ["admin", "warehouses"],
    queryFn: async () => (await api.get<Warehouse[]>("/admin/warehouses")).data,
  })
  const categoriesQuery = useQuery({
    queryKey: ["admin", "categories"],
    queryFn: async () => (await api.get<string[]>("/admin/categories")).data,
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

  // Load the saved product into the form, matrix included.
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
            values: attribute.values.map((value) => value.value).join(", "),
          }))
        : [{ name: "", values: "" }]
    )
    const next: Record<string, MatrixRow> = {}
    for (const variant of product.variants) {
      const quantity: Record<string, string> = {}
      for (const item of variant.stock) {
        quantity[item.warehouse_id] = String(item.quantity_on_hand)
      }
      const price: Record<string, string> = {}
      const entered: Record<string, string> = {}
      for (const item of variant.prices) {
        price[priceKey(item.tier_id, item.currency_code)] = String(item.unit_price)
        if (item.is_entered) entered[item.tier_id] = item.currency_code
      }
      next[variant.id] = {
        sku: variant.sku,
        unitCost: String(variant.unit_cost),
        quantity,
        price,
        entered,
      }
    }
    setMatrix(next)
  }, [product])

  /** Typing in one currency fills the rest of that tier's row from the rate. */
  const setPrice = (variantId: string, tierId: string, code: string, raw: string) => {
    setMatrix((current) => {
      const row = current[variantId]
      if (!row) return current
      const source = currencies.find((item) => item.code === code)
      const price = { ...row.price, [priceKey(tierId, code)]: raw }
      const amount = Number(raw)
      if (source && Number.isFinite(amount) && raw !== "") {
        for (const target of currencies) {
          if (target.code === code) continue
          const converted = (amount * source.rate_to_base) / target.rate_to_base
          price[priceKey(tierId, target.code)] = converted.toFixed(2)
        }
      }
      return {
        ...current,
        [variantId]: {
          ...row,
          price,
          entered: { ...row.entered, [tierId]: code },
        },
      }
    })
  }

  const setQuantity = (variantId: string, warehouseId: string, raw: string) => {
    setMatrix((current) => {
      const row = current[variantId]
      if (!row) return current
      return {
        ...current,
        [variantId]: { ...row, quantity: { ...row.quantity, [warehouseId]: raw } },
      }
    })
  }

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
          .filter((attribute) => attribute.name.trim() && attribute.values.trim())
          .map((attribute) => ({
            name: attribute.name.trim(),
            values: attribute.values
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean),
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
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] })
      await queryClient.invalidateQueries({ queryKey: ["admin", "catalog-stats"] })
      await queryClient.invalidateQueries({ queryKey: ["admin", "categories"] })
      if (isNew) {
        navigate(`/app/admin/products/${saved.id}`, { replace: true })
        toast.success("Product created. Now set its prices.")
        return
      }
      queryClient.setQueryData(["admin", "product", productId], saved)
      toast.success("Product saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the product.")),
  })

  const generate = useMutation({
    mutationFn: async () =>
      (await api.post<Product>(`/admin/products/${productId}/generate-variants`)).data,
    onSuccess: async (saved) => {
      queryClient.setQueryData(["admin", "product", productId], saved)
      await queryClient.invalidateQueries({ queryKey: ["admin", "catalog-stats"] })
      toast.success(`${saved.variants.length} variant(s) ready.`)
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not generate variants.")),
  })

  const saveMatrix = useMutation({
    mutationFn: async () => {
      const rows: VariantRowInput[] = (product?.variants ?? []).map((variant) => {
        const row = matrix[variant.id]
        return {
          id: variant.id,
          sku: row?.sku ?? variant.sku,
          unit_cost: Number(row?.unitCost ?? 0) || 0,
          // Only the cell the admin typed per tier; the server derives the rest.
          prices: tiers
            .map((tier) => {
              const code = row?.entered[tier.id] ?? baseCurrency?.code
              if (!code) return null
              const value = row?.price[priceKey(tier.id, code)]
              if (value === undefined || value === "") return null
              return {
                tier_id: tier.id,
                currency_code: code,
                unit_price: Number(value) || 0,
              }
            })
            .filter((entry): entry is NonNullable<typeof entry> => entry !== null),
          stock: warehouses
            .map((warehouse) => ({
              warehouse_id: warehouse.id,
              quantity_on_hand: Number(row?.quantity[warehouse.id] ?? 0) || 0,
            }))
            .filter(() => !isSubscription),
        }
      })
      return (await api.put<Product>(`/admin/products/${productId}/variants`, { rows })).data
    },
    onSuccess: async (saved) => {
      queryClient.setQueryData(["admin", "product", productId], saved)
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] })
      toast.success("Prices and stock saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the matrix.")),
  })

  const variants = product?.variants ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/app/admin/products">
            <ArrowLeftIcon className="size-4" />
            Product catalog
          </Link>
        </Button>
        <Button onClick={() => saveGeneral.mutate()} disabled={!name.trim() || !category.trim()}>
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
            />
            {/* Suggests names already in use, but accepts anything typed. */}
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
              onCheckedChange={setIsSubscription}
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
              One row per attribute, values comma separated. Generating builds every
              combination and leaves the ones you have already priced untouched.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-56">Attribute</TableHead>
                  <TableHead>Values</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {attributes.map((attribute, index) => (
                  <TableRow key={index}>
                    <TableCell>
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
                    <TableCell>
                      <Input
                        value={attribute.values}
                        placeholder="Black, Silver"
                        onChange={(event) =>
                          setAttributes((current) =>
                            current.map((item, position) =>
                              position === index
                                ? { ...item, values: event.target.value }
                                : item
                            )
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
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
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() =>
                  setAttributes((current) => [...current, { name: "", values: "" }])
                }
              >
                <PlusIcon className="size-4" />
                Add attribute
              </Button>
              <Button
                variant="secondary"
                disabled={isNew || generate.isPending}
                onClick={async () => {
                  await saveGeneral.mutateAsync()
                  generate.mutate()
                }}
              >
                <WandSparklesIcon className="size-4" />
                Generate variants
              </Button>
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
              Enter one currency per tier. The others fill in at the configured rate.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {hasVariants && <TableHead>Variant</TableHead>}
                  <TableHead className="w-56">SKU</TableHead>
                  <TableHead className="w-28">Unit cost</TableHead>
                  {!isSubscription &&
                    warehouses.map((warehouse) => (
                      <TableHead key={warehouse.id} className="w-28">
                        {warehouse.name}
                      </TableHead>
                    ))}
                  {tiers.flatMap((tier) =>
                    currencies.map((currency) => (
                      <TableHead key={`${tier.id}-${currency.code}`} className="w-32">
                        {tier.name} {currency.code}
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
                          className="h-8"
                          onChange={(event) =>
                            setMatrix((current) => ({
                              ...current,
                              [variant.id]: {
                                ...current[variant.id],
                                sku: event.target.value,
                              },
                            }))
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          className="h-8"
                          value={row?.unitCost ?? "0"}
                          onChange={(event) =>
                            setMatrix((current) => ({
                              ...current,
                              [variant.id]: {
                                ...current[variant.id],
                                unitCost: event.target.value,
                              },
                            }))
                          }
                        />
                      </TableCell>
                      {!isSubscription &&
                        warehouses.map((warehouse) => (
                          <TableCell key={warehouse.id}>
                            <Input
                              type="number"
                              min="0"
                              className="h-8"
                              value={row?.quantity[warehouse.id] ?? "0"}
                              onChange={(event) =>
                                setQuantity(variant.id, warehouse.id, event.target.value)
                              }
                            />
                          </TableCell>
                        ))}
                      {tiers.flatMap((tier) =>
                        currencies.map((currency) => (
                          <TableCell key={`${tier.id}-${currency.code}`}>
                            <Input
                              type="number"
                              min="0"
                              step="0.01"
                              className="h-8"
                              value={row?.price[priceKey(tier.id, currency.code)] ?? ""}
                              onChange={(event) =>
                                setPrice(
                                  variant.id,
                                  tier.id,
                                  currency.code,
                                  event.target.value
                                )
                              }
                            />
                          </TableCell>
                        ))
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            <Button onClick={() => saveMatrix.mutate()} disabled={saveMatrix.isPending}>
              Save prices and stock
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
