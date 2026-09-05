import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CopyPlusIcon,
  PlusIcon,
  SendIcon,
  Trash2Icon,
} from "lucide-react"
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
import { api, errorMessage } from "@/lib/api"
import type {
  Approval,
  Customer,
  Currency,
  Product,
  StockItem,
  Quotation,
  QuotationCreateInput,
  QuotationLine,
  QuotationLineCreateInput,
  QuotationLineUpdateInput,
  QuotationSubmitResponse,
  QuotationUpdateInput,
} from "@/types/api"

const money = (value: number, currency = "USD") =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value)

function approvalLabel(approval: Approval | null) {
  if (!approval) return "No approval record"
  return `${approval.risk_band.toUpperCase()} risk · ${approval.status.replaceAll("_", " ")}`
}

function LineEditor({
  quotationId,
  line,
  currency,
}: {
  quotationId: string
  line: QuotationLine
  currency: string
}) {
  const queryClient = useQueryClient()
  const [quantity, setQuantity] = useState(String(line.quantity))
  const [discount, setDiscount] = useState(String(line.line_discount_percent))

  useEffect(() => {
    setQuantity(String(line.quantity))
    setDiscount(String(line.line_discount_percent))
  }, [line.quantity, line.line_discount_percent])

  const save = useMutation({
    mutationFn: async () => {
      const body: QuotationLineUpdateInput = {
        quantity: Number(quantity),
        line_discount_percent: Number(discount),
      }
      const { data } = await api.patch<Quotation>(`/quotations/${quotationId}/lines/${line.id}`, body)
      return data
    },
    onSuccess: async (updated) => {
      queryClient.setQueryData(["quotation", quotationId], updated)
      await queryClient.invalidateQueries({ queryKey: ["quotations"] })
      toast.success("Line updated.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not update the line.")),
  })

  const remove = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<Quotation>(`/quotations/${quotationId}/lines/${line.id}`)
      return data
    },
    onSuccess: async (updated) => {
      queryClient.setQueryData(["quotation", quotationId], updated)
      await queryClient.invalidateQueries({ queryKey: ["quotations"] })
      toast.success("Line removed.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not remove the line.")),
  })

  return (
    <TableRow>
      <TableCell>
        <div className="space-y-1">
          <p className="font-medium">{line.product_name}</p>
          <p className="text-xs text-muted-foreground">
            {line.category ?? "—"} · {line.source}
          </p>
          <p className="text-xs text-muted-foreground">
            {line.warehouse_name
              ? `${line.warehouse_name} (${line.warehouse_code ?? "—"})`
              : "Warehouse not set"}
          </p>
        </div>
      </TableCell>
      <TableCell className="w-32 text-xs text-muted-foreground">
        {line.stock_available_at_entry != null
          ? `${line.stock_available_at_entry} available`
          : "—"}
      </TableCell>
      <TableCell className="w-24">
        <Input
          type="number"
          min="1"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
        />
      </TableCell>
      <TableCell className="w-28">
        <Input
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={discount}
          onChange={(event) => setDiscount(event.target.value)}
        />
      </TableCell>
      <TableCell className="text-right font-mono">{money(line.unit_price, currency)}</TableCell>
      <TableCell className="text-right font-mono">{money(line.line_total, currency)}</TableCell>
      <TableCell className="w-28">
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => save.mutate()}
            disabled={save.isPending}
          >
            Save
          </Button>
          <Button
            size="icon"
            className="size-8"
            variant="ghost"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            aria-label="Remove line"
          >
            <Trash2Icon className="size-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

export default function QuotationsPage() {
  const queryClient = useQueryClient()
  const [selectedQuotationId, setSelectedQuotationId] = useState<string | null>(null)
  const [isCreatingNew, setIsCreatingNew] = useState(false)

  const [customerId, setCustomerId] = useState("")
  const [currency, setCurrency] = useState("USD")
  const [recipientEmail, setRecipientEmail] = useState("")
  const [orderDiscount, setOrderDiscount] = useState("0")
  const [notes, setNotes] = useState("")

  const [newLineProductId, setNewLineProductId] = useState("")
  const [newLineVariantId, setNewLineVariantId] = useState("")
  const [newLineQuantity, setNewLineQuantity] = useState("1")
  const [newLineDiscount, setNewLineDiscount] = useState("0")

  const quotationsQuery = useQuery({
    queryKey: ["quotations"],
    queryFn: async () => (await api.get<Quotation[]>("/quotations")).data,
  })
  const customersQuery = useQuery({
    queryKey: ["lookups", "customers"],
    queryFn: async () => (await api.get<Customer[]>("/lookups/customers")).data,
  })
  const productsQuery = useQuery({
    queryKey: ["lookups", "products"],
    queryFn: async () => (await api.get<Product[]>("/lookups/products")).data,
  })
  const currenciesQuery = useQuery({
    queryKey: ["lookups", "currencies"],
    queryFn: async () => (await api.get<Currency[]>("/lookups/currencies")).data,
  })

  const selectedQuotationQuery = useQuery({
    queryKey: ["quotation", selectedQuotationId],
    queryFn: async () =>
      (await api.get<Quotation>(`/quotations/${selectedQuotationId}`)).data,
    enabled: Boolean(selectedQuotationId),
  })

  const quotations = quotationsQuery.data ?? []
  const customers = customersQuery.data ?? []
  const products = productsQuery.data ?? []
  const currencies = currenciesQuery.data ?? []
  const selectedQuotation = selectedQuotationQuery.data ?? null
  const selectedProduct = useMemo(
    () => products.find((product) => product.id === newLineProductId) ?? null,
    [products, newLineProductId]
  )
  const variantStockQuery = useQuery({
    queryKey: ["lookups", "variant-stock", newLineVariantId],
    queryFn: async () =>
      (await api.get<StockItem[]>(`/lookups/variants/${newLineVariantId}/stock`)).data,
    enabled: Boolean(newLineVariantId),
  })
  const variantStock = variantStockQuery.data ?? []
  const totalAvailable = variantStock.reduce(
    (sum, item) => sum + item.quantity_available,
    0
  )
  const requestedQuantity = Number(newLineQuantity) || 0
  // Short stock is a warning, not a block: splitting the order across
  // warehouses and backordering the rest is what fulfillment is for.
  const canAddLine =
    Boolean(selectedQuotationId) && Boolean(newLineVariantId) && requestedQuantity > 0

  const selectedCustomer = useMemo(
    () => customers.find((customer) => customer.id === customerId) ?? null,
    [customers, customerId]
  )

  useEffect(() => {
    if (!quotations.length || selectedQuotationId || isCreatingNew) return
    setSelectedQuotationId(quotations[0].id)
  }, [isCreatingNew, quotations, selectedQuotationId])

  useEffect(() => {
    const quote = selectedQuotation
    if (!quote) {
      return
    }
    setCustomerId(quote.customer_id)
    setCurrency(quote.currency)
    setRecipientEmail(quote.recipient_email ?? quote.customer.contact_email ?? "")
    setOrderDiscount(String(quote.order_discount_percent))
    setNotes(quote.notes ?? "")
    setNewLineProductId("")
    setNewLineVariantId("")
    setNewLineQuantity("1")
    setNewLineDiscount("0")
  }, [selectedQuotation])

  // A product with one hidden Default variant needs no second picker.
  useEffect(() => {
    if (!selectedProduct) {
      setNewLineVariantId("")
      return
    }
    setNewLineVariantId(
      selectedProduct.variants.length === 1 ? selectedProduct.variants[0].id : ""
    )
  }, [selectedProduct])

  useEffect(() => {
    if (!selectedQuotationId && customerId && !recipientEmail) {
      setRecipientEmail(selectedCustomer?.contact_email ?? "")
    }
  }, [customerId, recipientEmail, selectedCustomer, selectedQuotationId])

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["quotations"] }),
      queryClient.invalidateQueries({ queryKey: ["quotation"] }),
    ])
  }

  const persistHeader = useMutation({
    mutationFn: async () => {
      const body: QuotationCreateInput | QuotationUpdateInput = {
        customer_id: customerId,
        currency,
        recipient_email: recipientEmail || null,
        order_discount_percent: Number(orderDiscount) || 0,
        notes: notes || null,
      } as QuotationCreateInput

      if (selectedQuotationId) {
        const { data } = await api.patch<Quotation>(`/quotations/${selectedQuotationId}`, body)
        return data
      }

      const { data } = await api.post<Quotation>("/quotations", body)
      return data
    },
    onSuccess: async (quotation) => {
      queryClient.setQueryData(["quotation", quotation.id], quotation)
      setSelectedQuotationId(quotation.id)
      setIsCreatingNew(false)
      await invalidate()
      toast.success(selectedQuotationId ? "Quotation saved." : "Draft created.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the quotation.")),
  })

  const addLine = useMutation({
    mutationFn: async () => {
      if (!selectedQuotationId) throw new Error("Create or select a quotation first.")
      const body: QuotationLineCreateInput = {
        variant_id: newLineVariantId,
        quantity: Number(newLineQuantity),
        line_discount_percent: Number(newLineDiscount) || 0,
      }
      const { data } = await api.post<Quotation>(`/quotations/${selectedQuotationId}/lines`, body)
      return data
    },
    onSuccess: async (updated) => {
      queryClient.setQueryData(["quotation", updated.id], updated)
      await invalidate()
      setNewLineProductId("")
      setNewLineVariantId("")
      setNewLineQuantity("1")
      setNewLineDiscount("0")
      toast.success("Line added.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not add the line.")),
  })

  const submit = useMutation({
    mutationFn: async () => {
      if (!selectedQuotationId) throw new Error("Select a quotation first.")
      const { data } = await api.post<QuotationSubmitResponse>(
        `/quotations/${selectedQuotationId}/submit`
      )
      return data
    },
    onSuccess: async (result) => {
      queryClient.setQueryData(["quotation", result.quotation.id], result.quotation)
      await invalidate()
      toast.success(
        result.approval_required ? "Submitted for approval." : "Quotation approved."
      )
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not submit the quotation.")),
  })

  const selectedQuotationCurrency = selectedQuotation?.currency ?? "USD"
  const totalMargin = selectedQuotation?.margin_total ?? 0

  return (
    <>
      <PageHeader
        eyebrow="Sales"
        title="Quotations"
        description="Create a draft, add products, see margin, and submit when the discount crosses the allowed threshold."
        actions={
          <Button
            onClick={() => {
              setIsCreatingNew(true)
              setSelectedQuotationId(null)
              setCustomerId(customers[0]?.id ?? "")
              setCurrency(currencies[0]?.code ?? "USD")
              setRecipientEmail(customers[0]?.contact_email ?? "")
              setOrderDiscount("0")
              setNotes("")
              setNewLineProductId("")
            }}
          >
            <CopyPlusIcon className="size-4" />
            New Quotation
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Quotation list</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => {
                if (quotations[0]) {
                  setIsCreatingNew(false)
                  setSelectedQuotationId(quotations[0].id)
                }
              }}
            >
              <PlusIcon className="size-4" />
              Open latest draft
            </Button>
            <Separator />
            {quotationsQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
            {quotations.map((quotation) => (
              <button
                key={quotation.id}
                type="button"
                onClick={() => {
                  setIsCreatingNew(false)
                  setSelectedQuotationId(quotation.id)
                }}
                className={
                  "w-full rounded-lg border p-3 text-left transition-colors " +
                  (quotation.id === selectedQuotationId ? "border-primary bg-primary/5" : "hover:bg-muted/60")
                }
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{quotation.number}</p>
                    <p className="text-xs text-muted-foreground">{quotation.customer.name}</p>
                  </div>
                  <Badge variant={quotation.requires_approval ? "outline" : "secondary"}>
                    {quotation.status}
                  </Badge>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{quotation.lines.length} line(s)</span>
                  <span className="font-mono">{money(quotation.total, quotation.currency)}</span>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {selectedQuotationId ? "Edit quotation" : "Create draft quotation"}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Customer</Label>
                <Select value={customerId} onValueChange={setCustomerId}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Choose customer" />
                  </SelectTrigger>
                  <SelectContent>
                    {customers.map((customer) => (
                      <SelectItem key={customer.id} value={customer.id}>
                        {customer.name} · {customer.tier.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Currency</Label>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Choose currency" />
                  </SelectTrigger>
                  <SelectContent>
                    {currencies.map((item) => (
                      <SelectItem key={item.code} value={item.code}>
                        {item.code} · {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Prices come from the {selectedCustomer?.tier.name ?? "customer"} tier
                  in this currency.
                </p>
              </div>
              <div className="space-y-2">
                <Label>Recipient email</Label>
                <Input
                  type="email"
                  value={recipientEmail}
                  onChange={(event) => setRecipientEmail(event.target.value)}
                  placeholder="customer@company.com"
                />
                {selectedCustomer?.contact_email && (
                  <p className="text-xs text-muted-foreground">
                    Suggested from customer record: {selectedCustomer.contact_email}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label>Order discount %</Label>
                <Input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={orderDiscount}
                  onChange={(event) => setOrderDiscount(event.target.value)}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label>Notes</Label>
                <textarea
                  className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Optional internal notes"
                />
              </div>
              <div className="md:col-span-2 flex flex-wrap gap-2">
                <Button
                  onClick={() => persistHeader.mutate()}
                  disabled={persistHeader.isPending || !customerId}
                >
                  {persistHeader.isPending
                    ? "Saving…"
                    : selectedQuotationId
                      ? "Save draft"
                      : "Create draft"}
                </Button>
                {selectedQuotationId && (
                  <Button
                    variant="outline"
                    onClick={() => submit.mutate()}
                    disabled={submit.isPending}
                  >
                    <SendIcon className="size-4" />
                    Submit for approval
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {selectedQuotation && (
            <>
              <div className="grid gap-4 md:grid-cols-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Subtotal
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-2xl font-semibold">
                    {money(selectedQuotation.subtotal, selectedQuotationCurrency)}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Discount
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-2xl font-semibold">
                    {money(selectedQuotation.discount_total, selectedQuotationCurrency)}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Total
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-2xl font-semibold">
                    {money(selectedQuotation.total, selectedQuotationCurrency)}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Margin
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-2xl font-semibold">
                    {money(totalMargin, selectedQuotationCurrency)}
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Add product line</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label>Product</Label>
                    <Select value={newLineProductId} onValueChange={setNewLineProductId}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Choose product" />
                      </SelectTrigger>
                      <SelectContent>
                        {products.map((product) => (
                          <SelectItem key={product.id} value={product.id}>
                            {product.name} · {product.category}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {selectedProduct && selectedProduct.variants.length > 1 && (
                      <Select value={newLineVariantId} onValueChange={setNewLineVariantId}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Choose variant" />
                        </SelectTrigger>
                        <SelectContent>
                          {selectedProduct.variants.map((variant) => (
                            <SelectItem key={variant.id} value={variant.id}>
                              {variant.name} · {variant.sku}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    {newLineVariantId && (
                      <p className="text-xs text-muted-foreground">
                        {variantStock.length
                          ? `${totalAvailable} available across ${variantStock.length} warehouse(s)`
                          : "Not stock-tracked."}
                      </p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label>Quantity</Label>
                    <Input
                      type="number"
                      min="1"
                      value={newLineQuantity}
                      onChange={(event) => setNewLineQuantity(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Line discount %</Label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={newLineDiscount}
                      onChange={(event) => setNewLineDiscount(event.target.value)}
                    />
                  </div>
                  <div className="md:col-span-4">
                    <Button
                      onClick={() => addLine.mutate()}
                      disabled={addLine.isPending || !canAddLine}
                    >
                      <PlusIcon className="size-4" />
                      Add line
                    </Button>
                    {selectedProduct && selectedProduct.variants.length > 1 && !newLineVariantId && (
                      <p className="text-xs text-muted-foreground">
                        Choose a variant to price the line.
                      </p>
                    )}
                    {newLineVariantId && variantStock.length > 0 && requestedQuantity > totalAvailable && (
                      <p className="text-xs text-amber-600 dark:text-amber-500">
                        Only {totalAvailable} in stock. The line will be split across
                        warehouses and the remainder backordered.
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Lines</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Product</TableHead>
                        <TableHead className="w-40">Warehouse</TableHead>
                        <TableHead className="w-24">Qty</TableHead>
                        <TableHead className="w-28">Discount %</TableHead>
                        <TableHead className="text-right">Unit price</TableHead>
                        <TableHead className="text-right">Line total</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {selectedQuotation.lines.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                            Add the first line to build the quote.
                          </TableCell>
                        </TableRow>
                      ) : (
                        selectedQuotation.lines.map((line) => (
                          <LineEditor
                            key={line.id}
                            quotationId={selectedQuotation.id}
                            line={line}
                            currency={selectedQuotation.currency}
                          />
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    {selectedQuotation.requires_approval ? (
                      <AlertTriangleIcon className="size-4 text-amber-600" />
                    ) : (
                      <CheckCircle2Icon className="size-4 text-emerald-600" />
                    )}
                    Approval state
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={selectedQuotation.requires_approval ? "outline" : "secondary"}>
                      {selectedQuotation.requires_approval ? "Approval required" : "Auto-approved"}
                    </Badge>
                    <Badge variant="outline">{approvalLabel(selectedQuotation.approval)}</Badge>
                    <Badge variant="outline">Risk {selectedQuotation.risk_band}</Badge>
                  </div>
                  {selectedQuotation.approval?.steps?.length ? (
                    <div className="space-y-2">
                      {selectedQuotation.approval.steps.map((step) => (
                        <div key={step.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                          <div>
                            <p className="font-medium">{step.role}</p>
                            <p className="text-xs text-muted-foreground">
                              Step {step.step_order} · {step.status}
                            </p>
                          </div>
                          <div className="text-right text-xs text-muted-foreground">
                            {step.assignee_name ?? "Unassigned"}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Submit the quotation to create the approval record when governance is required.
                    </p>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  )
}
