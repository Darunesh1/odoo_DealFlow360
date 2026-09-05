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
  PriceList,
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
            {line.category_name ?? "—"} · {line.source}
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
  const [priceListId, setPriceListId] = useState("")
  const [recipientEmail, setRecipientEmail] = useState("")
  const [orderDiscount, setOrderDiscount] = useState("0")
  const [notes, setNotes] = useState("")

  const [newLineProductId, setNewLineProductId] = useState("")
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
  const priceListsQuery = useQuery({
    queryKey: ["lookups", "price-lists"],
    queryFn: async () => (await api.get<PriceList[]>("/lookups/price-lists")).data,
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
  const priceLists = priceListsQuery.data ?? []
  const selectedQuotation = selectedQuotationQuery.data ?? null
  const selectedProductStockQuery = useQuery({
    queryKey: ["lookups", "product-stock", newLineProductId],
    queryFn: async () =>
      (await api.get<StockItem[]>(`/lookups/products/${newLineProductId}/stock`)).data,
    enabled: Boolean(newLineProductId),
  })
  const selectedProductStock = selectedProductStockQuery.data ?? []
  const selectedWarehouse = selectedProductStock[0] ?? null
  const requestedQuantity = Number(newLineQuantity) || 0
  const canAddLine =
    Boolean(selectedQuotationId) &&
    Boolean(newLineProductId) &&
    Boolean(selectedWarehouse) &&
    requestedQuantity > 0 &&
    requestedQuantity <= (selectedWarehouse?.quantity_available ?? 0)

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
    setPriceListId(quote.price_list_id ?? "")
    setRecipientEmail(quote.recipient_email ?? quote.customer.contact_email ?? "")
    setOrderDiscount(String(quote.order_discount_percent))
    setNotes(quote.notes ?? "")
    setNewLineProductId("")
    setNewLineQuantity("1")
    setNewLineDiscount("0")
  }, [selectedQuotation])

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
        price_list_id: priceListId || null,
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
        product_id: newLineProductId,
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
              setPriceListId(customers[0]?.default_price_list_id ?? priceLists[0]?.id ?? "")
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
                <Label>Price list</Label>
                <Select value={priceListId} onValueChange={setPriceListId}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Choose price list" />
                  </SelectTrigger>
                  <SelectContent>
                    {priceLists.map((priceList) => (
                      <SelectItem key={priceList.id} value={priceList.id}>
                        {priceList.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                            {product.name} · {product.sku}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {newLineProductId && (
                      <p className="text-xs text-muted-foreground">
                        {selectedWarehouse
                          ? `Warehouse: ${selectedWarehouse.warehouse_name} (${selectedWarehouse.warehouse_code}) · ${selectedWarehouse.quantity_available} available`
                          : "No active warehouse stock available for this product."}
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
                    {newLineProductId && !selectedWarehouse && (
                      <p className="text-xs text-muted-foreground">
                        This product has no active warehouse stock available.
                      </p>
                    )}
                    {selectedWarehouse && requestedQuantity > selectedWarehouse.quantity_available && (
                      <p className="text-xs text-muted-foreground">
                        Requested quantity exceeds the available stock in the selected warehouse.
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
