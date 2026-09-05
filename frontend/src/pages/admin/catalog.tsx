import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, SaveIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, errorMessage } from "@/lib/api"
import type {
  Customer,
  CustomerCreateInput,
  CustomerTier,
  CustomerTierCreateInput,
  CustomerTierUpdateInput,
  CustomerUpdateInput,
  PriceList,
  PriceListCreateInput,
  PriceListItem,
  PriceListItemUpsertInput,
  PriceListUpdateInput,
  Product,
  ProductCategory,
  ProductCategoryCreateInput,
  ProductCategoryUpdateInput,
  ProductCreateInput,
  ProductUpdateInput,
  StockItem,
  StockUpsertInput,
  Warehouse,
  WarehouseCreateInput,
  WarehouseUpdateInput,
} from "@/types/api"

const money = (value: number, currency = "USD") =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value)

export default function CatalogPage() {
  const queryClient = useQueryClient()

  const tiersQuery = useQuery({
    queryKey: ["customer-tiers"],
    queryFn: async () => (await api.get<CustomerTier[]>("/admin/customer-tiers")).data,
  })
  const categoriesQuery = useQuery({
    queryKey: ["product-categories"],
    queryFn: async () => (await api.get<ProductCategory[]>("/admin/product-categories")).data,
  })
  const productsQuery = useQuery({
    queryKey: ["products"],
    queryFn: async () => (await api.get<Product[]>("/admin/products")).data,
  })
  const priceListsQuery = useQuery({
    queryKey: ["price-lists"],
    queryFn: async () => (await api.get<PriceList[]>("/admin/price-lists")).data,
  })
  const warehousesQuery = useQuery({
    queryKey: ["warehouses"],
    queryFn: async () => (await api.get<Warehouse[]>("/admin/warehouses")).data,
  })
  const stockQuery = useQuery({
    queryKey: ["stock"],
    queryFn: async () => (await api.get<StockItem[]>("/admin/stock")).data,
  })
  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: async () => (await api.get<Customer[]>("/admin/customers")).data,
  })

  const tiers = tiersQuery.data ?? []
  const categories = categoriesQuery.data ?? []
  const products = productsQuery.data ?? []
  const priceLists = priceListsQuery.data ?? []
  const warehouses = warehousesQuery.data ?? []
  const stock = stockQuery.data ?? []
  const customers = customersQuery.data ?? []

  const [tierId, setTierId] = useState("")
  const [tierCode, setTierCode] = useState("")
  const [tierName, setTierName] = useState("")
  const [tierMaxDiscount, setTierMaxDiscount] = useState("0")
  const [tierSortOrder, setTierSortOrder] = useState("0")
  const [tierActive, setTierActive] = useState(true)

  const [categoryId, setCategoryId] = useState("")
  const [categoryCode, setCategoryCode] = useState("")
  const [categoryName, setCategoryName] = useState("")
  const [categoryMaxDiscount, setCategoryMaxDiscount] = useState("0")
  const [categorySortOrder, setCategorySortOrder] = useState("0")
  const [categoryActive, setCategoryActive] = useState(true)

  const [productId, setProductId] = useState("")
  const [productSku, setProductSku] = useState("")
  const [productName, setProductName] = useState("")
  const [productCategoryId, setProductCategoryId] = useState("")
  const [productDescription, setProductDescription] = useState("")
  const [productListPrice, setProductListPrice] = useState("0")
  const [productUnitCost, setProductUnitCost] = useState("0")
  const [productUnit, setProductUnit] = useState("each")
  const [productTax, setProductTax] = useState("0")
  const [productSubscription, setProductSubscription] = useState(false)
  const [productRecurringInterval, setProductRecurringInterval] = useState("none")
  const [productActive, setProductActive] = useState(true)

  const [priceListId, setPriceListId] = useState("")
  const [priceListName, setPriceListName] = useState("")
  const [priceListTierId, setPriceListTierId] = useState("none")
  const [priceListCurrency, setPriceListCurrency] = useState("USD")
  const [priceListAdjustment, setPriceListAdjustment] = useState("0")
  const [priceListActive, setPriceListActive] = useState(true)
  const [priceListItemProductId, setPriceListItemProductId] = useState("")
  const [priceListItemUnitPrice, setPriceListItemUnitPrice] = useState("0")

  const [warehouseId, setWarehouseId] = useState("")
  const [warehouseCode, setWarehouseCode] = useState("")
  const [warehouseName, setWarehouseName] = useState("")
  const [warehouseAddress, setWarehouseAddress] = useState("")
  const [warehouseBaseCost, setWarehouseBaseCost] = useState("0")
  const [warehousePerUnit, setWarehousePerUnit] = useState("0")
  const [warehouseWeight, setWarehouseWeight] = useState("1")
  const [warehousePriority, setWarehousePriority] = useState("100")
  const [warehouseActive, setWarehouseActive] = useState(true)

  const [stockWarehouseId, setStockWarehouseId] = useState("")
  const [stockProductId, setStockProductId] = useState("")
  const [stockOnHand, setStockOnHand] = useState("0")
  const [stockReserved, setStockReserved] = useState("0")
  const [stockReorderPoint, setStockReorderPoint] = useState("0")
  const [stockReorderQty, setStockReorderQty] = useState("0")
  const [stockLeadTime, setStockLeadTime] = useState("0")
  const [stockBinLocation, setStockBinLocation] = useState("")

  const [customerId, setCustomerId] = useState("")
  const [customerName, setCustomerName] = useState("")
  const [customerTierId, setCustomerTierId] = useState("")
  const [customerDefaultPriceListId, setCustomerDefaultPriceListId] = useState("none")
  const [customerEmail, setCustomerEmail] = useState("")
  const [customerPhone, setCustomerPhone] = useState("")
  const [customerBilling, setCustomerBilling] = useState("")
  const [customerActive, setCustomerActive] = useState(true)

  useEffect(() => {
    if (!tierId && tiers[0]) {
      setTierId(tiers[0].id)
    }
    if (!categoryId && categories[0]) {
      setCategoryId(categories[0].id)
    }
    if (!productCategoryId && categories[0]) {
      setProductCategoryId(categories[0].id)
    }
    if (!priceListId && priceLists[0]) {
      setPriceListId(priceLists[0].id)
    }
    if (!priceListTierId && tiers[0]) {
      setPriceListTierId(tiers[0].id)
    }
    if (!warehouseId && warehouses[0]) {
      setWarehouseId(warehouses[0].id)
    }
    if (!stockWarehouseId && warehouses[0]) {
      setStockWarehouseId(warehouses[0].id)
    }
    if (!stockProductId && products[0]) {
      setStockProductId(products[0].id)
    }
    if (!customerTierId && tiers[0]) {
      setCustomerTierId(tiers[0].id)
    }
    if (!customerDefaultPriceListId && priceLists[0]) {
      setCustomerDefaultPriceListId(priceLists[0].id)
    }
  }, [tiers, categories, products, priceLists, warehouses, tierId, categoryId, productCategoryId, priceListId, priceListTierId, warehouseId, stockWarehouseId, stockProductId, customerTierId, customerDefaultPriceListId])

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["customer-tiers"] }),
      queryClient.invalidateQueries({ queryKey: ["product-categories"] }),
      queryClient.invalidateQueries({ queryKey: ["products"] }),
      queryClient.invalidateQueries({ queryKey: ["price-lists"] }),
      queryClient.invalidateQueries({ queryKey: ["warehouses"] }),
      queryClient.invalidateQueries({ queryKey: ["stock"] }),
      queryClient.invalidateQueries({ queryKey: ["customers"] }),
    ])
  }

  const tierSave = useMutation({
    mutationFn: async () => {
      const body: CustomerTierCreateInput | CustomerTierUpdateInput = {
        code: tierCode,
        name: tierName,
        max_discount_percent: Number(tierMaxDiscount) || 0,
        sort_order: Number(tierSortOrder) || 0,
        is_active: tierActive,
      }
      if (tierId) {
        const { data } = await api.patch<CustomerTier>(`/admin/customer-tiers/${tierId}`, body)
        return data
      }
      const { data } = await api.post<CustomerTier>("/admin/customer-tiers", body)
      return data
    },
    onSuccess: async (saved) => {
      setTierId(saved.id)
      await invalidateAll()
      toast.success("Customer tier saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the tier.")),
  })

  const categorySave = useMutation({
    mutationFn: async () => {
      const body: ProductCategoryCreateInput | ProductCategoryUpdateInput = {
        code: categoryCode,
        name: categoryName,
        max_discount_percent: Number(categoryMaxDiscount) || 0,
        sort_order: Number(categorySortOrder) || 0,
        is_active: categoryActive,
      }
      if (categoryId) {
        const { data } = await api.patch<ProductCategory>(
          `/admin/product-categories/${categoryId}`,
          body
        )
        return data
      }
      const { data } = await api.post<ProductCategory>("/admin/product-categories", body)
      return data
    },
    onSuccess: async (saved) => {
      setCategoryId(saved.id)
      await invalidateAll()
      toast.success("Category saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the category.")),
  })

  const productSave = useMutation({
    mutationFn: async () => {
      const recurringInterval =
        productRecurringInterval === "none"
          ? null
          : (productRecurringInterval as "weekly" | "monthly" | "quarterly" | "yearly")
      const body: ProductCreateInput | ProductUpdateInput = {
        sku: productSku,
        name: productName,
        category_id: productCategoryId,
        description: productDescription || null,
        list_price: Number(productListPrice) || 0,
        unit_cost: Number(productUnitCost) || 0,
        unit: productUnit as ProductCreateInput["unit"],
        tax_percent: Number(productTax) || 0,
        is_subscription: productSubscription,
        recurring_interval: recurringInterval,
        is_active: productActive,
      }
      if (productId) {
        const { data } = await api.patch<Product>(`/admin/products/${productId}`, body)
        return data
      }
      const { data } = await api.post<Product>("/admin/products", body)
      return data
    },
    onSuccess: async (saved) => {
      setProductId(saved.id)
      await invalidateAll()
      toast.success("Product saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the product.")),
  })

  const priceListSave = useMutation({
    mutationFn: async () => {
      const body: PriceListCreateInput | PriceListUpdateInput = {
        name: priceListName,
        tier_id: priceListTierId === "none" ? null : priceListTierId,
        currency: priceListCurrency,
        adjustment_percent: Number(priceListAdjustment) || 0,
        is_active: priceListActive,
      }
      if (priceListId) {
        const { data } = await api.patch<PriceList>(`/admin/price-lists/${priceListId}`, body)
        return data
      }
      const { data } = await api.post<PriceList>("/admin/price-lists", body)
      return data
    },
    onSuccess: async (saved) => {
      setPriceListId(saved.id)
      await invalidateAll()
      toast.success("Price list saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the price list.")),
  })

  const priceListItemSave = useMutation({
    mutationFn: async () => {
      if (!priceListId) throw new Error("Select a price list first.")
      const body: PriceListItemUpsertInput = {
        product_id: priceListItemProductId,
        unit_price: Number(priceListItemUnitPrice) || 0,
      }
      const { data } = await api.post<PriceListItem>(`/admin/price-lists/${priceListId}/items`, body)
      return data
    },
    onSuccess: async () => {
      await invalidateAll()
      toast.success("Price list item saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the item.")),
  })

  const warehouseSave = useMutation({
    mutationFn: async () => {
      const body: WarehouseCreateInput | WarehouseUpdateInput = {
        code: warehouseCode,
        name: warehouseName,
        address: warehouseAddress || null,
        shipping_base_cost: Number(warehouseBaseCost) || 0,
        shipping_cost_per_unit: Number(warehousePerUnit) || 0,
        shipping_cost_weight: Number(warehouseWeight) || 1,
        split_priority: Number(warehousePriority) || 100,
        is_active: warehouseActive,
      }
      if (warehouseId) {
        const { data } = await api.patch<Warehouse>(`/admin/warehouses/${warehouseId}`, body)
        return data
      }
      const { data } = await api.post<Warehouse>("/admin/warehouses", body)
      return data
    },
    onSuccess: async (saved) => {
      setWarehouseId(saved.id)
      await invalidateAll()
      toast.success("Warehouse saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the warehouse.")),
  })

  const stockSave = useMutation({
    mutationFn: async () => {
      const body: StockUpsertInput = {
        warehouse_id: stockWarehouseId,
        product_id: stockProductId,
        quantity_on_hand: Number(stockOnHand) || 0,
        quantity_reserved: Number(stockReserved) || 0,
        reorder_point: Number(stockReorderPoint) || 0,
        reorder_quantity: Number(stockReorderQty) || 0,
        lead_time_days: Number(stockLeadTime) || 0,
        bin_location: stockBinLocation || null,
      }
      const { data } = await api.post<StockItem>("/admin/stock", body)
      return data
    },
    onSuccess: async () => {
      await invalidateAll()
      toast.success("Stock saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the stock.")),
  })

  const customerSave = useMutation({
    mutationFn: async () => {
      const body: CustomerCreateInput | CustomerUpdateInput = {
        name: customerName,
        tier_id: customerTierId,
        default_price_list_id:
          customerDefaultPriceListId === "none" ? null : customerDefaultPriceListId,
        contact_email: customerEmail || null,
        phone: customerPhone || null,
        billing_address: customerBilling || null,
        is_active: customerActive,
      }
      if (customerId) {
        const { data } = await api.patch<Customer>(`/admin/customers/${customerId}`, body)
        return data
      }
      const { data } = await api.post<Customer>("/admin/customers", body)
      return data
    },
    onSuccess: async (saved) => {
      setCustomerId(saved.id)
      await invalidateAll()
      toast.success("Customer saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the customer.")),
  })

  const currentPriceListItems = useMemo(
    () => priceLists.find((item) => item.id === priceListId)?.items ?? [],
    [priceLists, priceListId]
  )

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Catalog"
        description="Manage the master data needed for quotations: tiers, categories, products, price lists, warehouses, stock, and customers."
      />

      <Tabs defaultValue="tiers" className="space-y-4">
        <TabsList className="w-full flex-wrap justify-start">
          <TabsTrigger value="tiers">Customer tiers</TabsTrigger>
          <TabsTrigger value="categories">Categories</TabsTrigger>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="prices">Price lists</TabsTrigger>
          <TabsTrigger value="inventory">Inventory</TabsTrigger>
          <TabsTrigger value="customers">Customers</TabsTrigger>
        </TabsList>

        <TabsContent value="tiers" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Customer tier</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Code</Label>
                <Input value={tierCode} onChange={(e) => setTierCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Name</Label>
                <Input value={tierName} onChange={(e) => setTierName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Max discount %</Label>
                <Input type="number" value={tierMaxDiscount} onChange={(e) => setTierMaxDiscount(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Sort order</Label>
                <Input type="number" value={tierSortOrder} onChange={(e) => setTierSortOrder(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={tierActive} onChange={(e) => setTierActive(e.target.checked)} />
                Active
              </label>
              <div>
                <Button onClick={() => tierSave.mutate()} disabled={tierSave.isPending}>
                  <SaveIcon className="size-4" />
                  Save tier
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Code</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Discount</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tiers.map((tier) => (
                    <TableRow key={tier.id} onClick={() => {
                      setTierId(tier.id)
                      setTierCode(tier.code)
                      setTierName(tier.name)
                      setTierMaxDiscount(String(tier.max_discount_percent))
                      setTierSortOrder(String(tier.sort_order))
                      setTierActive(tier.is_active)
                    }} className="cursor-pointer">
                      <TableCell>{tier.code}</TableCell>
                      <TableCell>{tier.name}</TableCell>
                      <TableCell>{tier.max_discount_percent}%</TableCell>
                      <TableCell>{tier.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="categories" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Product category</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label>Code</Label><Input value={categoryCode} onChange={(e) => setCategoryCode(e.target.value)} /></div>
              <div className="space-y-2"><Label>Name</Label><Input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} /></div>
              <div className="space-y-2"><Label>Max discount %</Label><Input type="number" value={categoryMaxDiscount} onChange={(e) => setCategoryMaxDiscount(e.target.value)} /></div>
              <div className="space-y-2"><Label>Sort order</Label><Input type="number" value={categorySortOrder} onChange={(e) => setCategorySortOrder(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={categoryActive} onChange={(e) => setCategoryActive(e.target.checked)} />Active</label>
              <div><Button onClick={() => categorySave.mutate()} disabled={categorySave.isPending}><SaveIcon className="size-4" />Save category</Button></div>
            </CardContent>
          </Card>
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Discount</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {categories.map((category) => (
                  <TableRow key={category.id} className="cursor-pointer" onClick={() => {
                    setCategoryId(category.id)
                    setCategoryCode(category.code)
                    setCategoryName(category.name)
                    setCategoryMaxDiscount(String(category.max_discount_percent ?? 0))
                    setCategorySortOrder(String(category.sort_order))
                    setCategoryActive(category.is_active)
                  }}>
                    <TableCell>{category.code}</TableCell><TableCell>{category.name}</TableCell><TableCell>{category.max_discount_percent ?? 0}%</TableCell><TableCell>{category.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="products" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Product</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label>SKU</Label><Input value={productSku} onChange={(e) => setProductSku(e.target.value)} /></div>
              <div className="space-y-2"><Label>Name</Label><Input value={productName} onChange={(e) => setProductName(e.target.value)} /></div>
              <div className="space-y-2 md:col-span-2"><Label>Category</Label><Select value={productCategoryId} onValueChange={setProductCategoryId}><SelectTrigger className="w-full"><SelectValue placeholder="Choose category" /></SelectTrigger><SelectContent>{categories.map((category) => <SelectItem key={category.id} value={category.id}>{category.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2 md:col-span-2"><Label>Description</Label><Input value={productDescription} onChange={(e) => setProductDescription(e.target.value)} /></div>
              <div className="space-y-2"><Label>List price</Label><Input type="number" value={productListPrice} onChange={(e) => setProductListPrice(e.target.value)} /></div>
              <div className="space-y-2"><Label>Cost</Label><Input type="number" value={productUnitCost} onChange={(e) => setProductUnitCost(e.target.value)} /></div>
              <div className="space-y-2"><Label>Unit</Label><Select value={productUnit} onValueChange={setProductUnit}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="each">Each</SelectItem><SelectItem value="hour">Hour</SelectItem><SelectItem value="day">Day</SelectItem><SelectItem value="license">License</SelectItem><SelectItem value="recurring">Recurring</SelectItem></SelectContent></Select></div>
              <div className="space-y-2"><Label>Tax %</Label><Input type="number" value={productTax} onChange={(e) => setProductTax(e.target.value)} /></div>
              <div className="space-y-2"><Label>Recurring interval</Label><Select value={productRecurringInterval} onValueChange={setProductRecurringInterval}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="quarterly">Quarterly</SelectItem><SelectItem value="yearly">Yearly</SelectItem></SelectContent></Select></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={productSubscription} onChange={(e) => setProductSubscription(e.target.checked)} />Subscription</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={productActive} onChange={(e) => setProductActive(e.target.checked)} />Active</label>
              <div className="md:col-span-2"><Button onClick={() => productSave.mutate()} disabled={productSave.isPending}><SaveIcon className="size-4" />Save product</Button></div>
            </CardContent>
          </Card>
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>SKU</TableHead><TableHead>Name</TableHead><TableHead>Category</TableHead><TableHead>Price</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {products.map((product) => (
                  <TableRow key={product.id} className="cursor-pointer" onClick={() => {
                    setProductId(product.id)
                    setProductSku(product.sku)
                    setProductName(product.name)
                    setProductCategoryId(product.category_id)
                    setProductDescription(product.description ?? "")
                    setProductListPrice(String(product.list_price))
                    setProductUnitCost(String(product.unit_cost))
                    setProductUnit(product.unit)
                    setProductTax(String(product.tax_percent))
                    setProductSubscription(product.is_subscription)
                    setProductRecurringInterval(product.recurring_interval ?? "none")
                    setProductActive(product.is_active)
                  }}>
                    <TableCell>{product.sku}</TableCell>
                    <TableCell>{product.name}</TableCell>
                    <TableCell>{product.category.name}</TableCell>
                    <TableCell>{money(product.list_price)}</TableCell>
                    <TableCell>{product.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="prices" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Price list</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label>Name</Label><Input value={priceListName} onChange={(e) => setPriceListName(e.target.value)} /></div>
              <div className="space-y-2"><Label>Tier</Label><Select value={priceListTierId} onValueChange={setPriceListTierId}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No tier</SelectItem>{tiers.map((tier) => <SelectItem key={tier.id} value={tier.id}>{tier.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label>Currency</Label><Input value={priceListCurrency} onChange={(e) => setPriceListCurrency(e.target.value.toUpperCase())} /></div>
              <div className="space-y-2"><Label>Adjustment %</Label><Input type="number" value={priceListAdjustment} onChange={(e) => setPriceListAdjustment(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={priceListActive} onChange={(e) => setPriceListActive(e.target.checked)} />Active</label>
              <div><Button onClick={() => priceListSave.mutate()} disabled={priceListSave.isPending}><SaveIcon className="size-4" />Save price list</Button></div>
            </CardContent>
          </Card>

          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Tier</TableHead><TableHead>Currency</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {priceLists.map((list) => (
                  <TableRow key={list.id} className="cursor-pointer" onClick={() => {
                    setPriceListId(list.id)
                    setPriceListName(list.name)
                    setPriceListTierId(list.tier_id ?? "none")
                    setPriceListCurrency(list.currency)
                    setPriceListAdjustment(String(list.adjustment_percent))
                    setPriceListActive(list.is_active)
                    setPriceListItemProductId(list.items[0]?.product_id ?? products[0]?.id ?? "")
                  }}>
                    <TableCell>{list.name}</TableCell><TableCell>{list.tier?.name ?? "All"}</TableCell><TableCell>{list.currency}</TableCell><TableCell>{list.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Price list items · {priceLists.find((item) => item.id === priceListId)?.name ?? "Select a price list"}</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2 md:col-span-2"><Label>Product</Label><Select value={priceListItemProductId} onValueChange={setPriceListItemProductId}><SelectTrigger className="w-full"><SelectValue placeholder="Choose product" /></SelectTrigger><SelectContent>{products.map((product) => <SelectItem key={product.id} value={product.id}>{product.name} · {product.sku}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label>Unit price</Label><Input type="number" value={priceListItemUnitPrice} onChange={(e) => setPriceListItemUnitPrice(e.target.value)} /></div>
              <div className="md:col-span-3"><Button onClick={() => priceListItemSave.mutate()} disabled={priceListItemSave.isPending || !priceListId}><PlusIcon className="size-4" />Save price override</Button></div>
              <div className="md:col-span-3">
                <Separator className="my-2" />
                <Table>
                  <TableHeader><TableRow><TableHead>SKU</TableHead><TableHead>Product</TableHead><TableHead className="text-right">Unit price</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {currentPriceListItems.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>{item.sku}</TableCell>
                        <TableCell>{item.product_name}</TableCell>
                        <TableCell className="text-right">{money(item.unit_price, priceLists.find((list) => list.id === priceListId)?.currency ?? "USD")}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="inventory" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Warehouse</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label>Code</Label><Input value={warehouseCode} onChange={(e) => setWarehouseCode(e.target.value)} /></div>
              <div className="space-y-2"><Label>Name</Label><Input value={warehouseName} onChange={(e) => setWarehouseName(e.target.value)} /></div>
              <div className="space-y-2 md:col-span-2"><Label>Address</Label><Input value={warehouseAddress} onChange={(e) => setWarehouseAddress(e.target.value)} /></div>
              <div className="space-y-2"><Label>Base shipping</Label><Input type="number" value={warehouseBaseCost} onChange={(e) => setWarehouseBaseCost(e.target.value)} /></div>
              <div className="space-y-2"><Label>Per unit shipping</Label><Input type="number" value={warehousePerUnit} onChange={(e) => setWarehousePerUnit(e.target.value)} /></div>
              <div className="space-y-2"><Label>Weight</Label><Input type="number" value={warehouseWeight} onChange={(e) => setWarehouseWeight(e.target.value)} /></div>
              <div className="space-y-2"><Label>Priority</Label><Input type="number" value={warehousePriority} onChange={(e) => setWarehousePriority(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={warehouseActive} onChange={(e) => setWarehouseActive(e.target.checked)} />Active</label>
              <div><Button onClick={() => warehouseSave.mutate()} disabled={warehouseSave.isPending}><SaveIcon className="size-4" />Save warehouse</Button></div>
            </CardContent>
          </Card>

          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Priority</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {warehouses.map((warehouse) => (
                  <TableRow key={warehouse.id} className="cursor-pointer" onClick={() => {
                    setWarehouseId(warehouse.id)
                    setWarehouseCode(warehouse.code)
                    setWarehouseName(warehouse.name)
                    setWarehouseAddress(warehouse.address ?? "")
                    setWarehouseBaseCost(String(warehouse.shipping_base_cost))
                    setWarehousePerUnit(String(warehouse.shipping_cost_per_unit))
                    setWarehouseWeight(String(warehouse.shipping_cost_weight))
                    setWarehousePriority(String(warehouse.split_priority))
                    setWarehouseActive(warehouse.is_active)
                  }}>
                    <TableCell>{warehouse.code}</TableCell><TableCell>{warehouse.name}</TableCell><TableCell>{warehouse.split_priority}</TableCell><TableCell>{warehouse.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Stock</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2 md:col-span-2"><Label>Warehouse</Label><Select value={stockWarehouseId} onValueChange={setStockWarehouseId}><SelectTrigger className="w-full"><SelectValue placeholder="Choose warehouse" /></SelectTrigger><SelectContent>{warehouses.map((warehouse) => <SelectItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2 md:col-span-2"><Label>Product</Label><Select value={stockProductId} onValueChange={setStockProductId}><SelectTrigger className="w-full"><SelectValue placeholder="Choose product" /></SelectTrigger><SelectContent>{products.map((product) => <SelectItem key={product.id} value={product.id}>{product.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label>On hand</Label><Input type="number" value={stockOnHand} onChange={(e) => setStockOnHand(e.target.value)} /></div>
              <div className="space-y-2"><Label>Reserved</Label><Input type="number" value={stockReserved} onChange={(e) => setStockReserved(e.target.value)} /></div>
              <div className="space-y-2"><Label>Reorder point</Label><Input type="number" value={stockReorderPoint} onChange={(e) => setStockReorderPoint(e.target.value)} /></div>
              <div className="space-y-2"><Label>Reorder qty</Label><Input type="number" value={stockReorderQty} onChange={(e) => setStockReorderQty(e.target.value)} /></div>
              <div className="space-y-2"><Label>Lead time days</Label><Input type="number" value={stockLeadTime} onChange={(e) => setStockLeadTime(e.target.value)} /></div>
              <div className="space-y-2"><Label>Bin location</Label><Input value={stockBinLocation} onChange={(e) => setStockBinLocation(e.target.value)} /></div>
              <div className="md:col-span-3"><Button onClick={() => stockSave.mutate()} disabled={stockSave.isPending}><SaveIcon className="size-4" />Save stock</Button></div>
            </CardContent>
          </Card>

          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Warehouse</TableHead><TableHead>Product</TableHead><TableHead className="text-right">Available</TableHead><TableHead>Bin</TableHead></TableRow></TableHeader>
              <TableBody>
                {stock.map((item) => (
                  <TableRow key={item.id} className="cursor-pointer" onClick={() => {
                    setStockWarehouseId(item.warehouse_id)
                    setStockProductId(item.product_id)
                    setStockOnHand(String(item.quantity_on_hand))
                    setStockReserved(String(item.quantity_reserved))
                    setStockReorderPoint(String(item.reorder_point))
                    setStockReorderQty(String(item.reorder_quantity))
                    setStockLeadTime(String(item.lead_time_days))
                    setStockBinLocation(item.bin_location ?? "")
                  }}>
                    <TableCell>{item.warehouse_name}</TableCell><TableCell>{item.product_name}</TableCell><TableCell className="text-right">{item.quantity_available}</TableCell><TableCell>{item.bin_location ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="customers" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Customer</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2"><Label>Name</Label><Input value={customerName} onChange={(e) => setCustomerName(e.target.value)} /></div>
              <div className="space-y-2"><Label>Tier</Label><Select value={customerTierId} onValueChange={setCustomerTierId}><SelectTrigger className="w-full"><SelectValue placeholder="Choose tier" /></SelectTrigger><SelectContent>{tiers.map((tier) => <SelectItem key={tier.id} value={tier.id}>{tier.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label>Default price list</Label><Select value={customerDefaultPriceListId} onValueChange={setCustomerDefaultPriceListId}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem>{priceLists.map((list) => <SelectItem key={list.id} value={list.id}>{list.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label>Email</Label><Input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} /></div>
              <div className="space-y-2"><Label>Phone</Label><Input value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} /></div>
              <div className="space-y-2"><Label>Billing address</Label><Input value={customerBilling} onChange={(e) => setCustomerBilling(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={customerActive} onChange={(e) => setCustomerActive(e.target.checked)} />Active</label>
              <div><Button onClick={() => customerSave.mutate()} disabled={customerSave.isPending}><SaveIcon className="size-4" />Save customer</Button></div>
            </CardContent>
          </Card>

          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Tier</TableHead><TableHead>Email</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
              <TableBody>
                {customers.map((customer) => (
                  <TableRow key={customer.id} className="cursor-pointer" onClick={() => {
                    setCustomerId(customer.id)
                    setCustomerName(customer.name)
                    setCustomerTierId(customer.tier_id)
                    setCustomerDefaultPriceListId(customer.default_price_list_id ?? "none")
                    setCustomerEmail(customer.contact_email ?? "")
                    setCustomerPhone(customer.phone ?? "")
                    setCustomerBilling(customer.billing_address ?? "")
                    setCustomerActive(customer.is_active)
                  }}>
                    <TableCell>{customer.name}</TableCell><TableCell>{customer.tier.name}</TableCell><TableCell>{customer.contact_email ?? "—"}</TableCell><TableCell>{customer.is_active ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Inactive</Badge>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </>
  )
}
