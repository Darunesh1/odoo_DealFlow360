import { useMemo, useState } from "react"
import { CheckIcon, PlusIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import type { PickerProduct, PickerVariant } from "@/types/api"

/**
 * Add-a-line, grouped by category as the spec's B3 describes ("Hardware,
 * Services, Subscriptions").
 *
 * The variant select only appears when there is a choice to make: a product
 * with a single hidden Default variant should not ask the rep to pick it.
 */
export function ProductPicker({
  products,
  disabled,
  onAdd,
}: {
  products: PickerProduct[]
  disabled: boolean
  onAdd: (input: { variantId: string; quantity: number; discount: number }) => void
}) {
  const [open, setOpen] = useState(false)
  const [productId, setProductId] = useState("")
  const [variantId, setVariantId] = useState("")
  const [quantity, setQuantity] = useState("1")
  const [discount, setDiscount] = useState("0")

  const product = products.find((item) => item.id === productId)
  const variants = useMemo(
    () => (product?.variants ?? []).filter((variant) => variant.is_active),
    [product]
  )
  const chosenVariant: PickerVariant | undefined =
    variants.find((variant) => variant.id === variantId) ??
    (variants.length === 1 ? variants[0] : undefined)

  const grouped = useMemo(() => {
    const buckets = new Map<string, PickerProduct[]>()
    for (const item of products) {
      const list = buckets.get(item.category) ?? []
      list.push(item)
      buckets.set(item.category, list)
    }
    return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [products])

  const pick = (id: string) => {
    setProductId(id)
    const next = products.find((item) => item.id === id)
    const active = (next?.variants ?? []).filter((variant) => variant.is_active)
    // One variant means no decision to make.
    setVariantId(active.length === 1 ? active[0].id : "")
    setOpen(false)
  }

  const submit = () => {
    if (!chosenVariant) return
    onAdd({
      variantId: chosenVariant.id,
      quantity: Math.max(1, Number(quantity) || 1),
      discount: Math.min(100, Math.max(0, Number(discount) || 0)),
    })
    setProductId("")
    setVariantId("")
    setQuantity("1")
    setDiscount("0")
  }

  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1.4fr)_6rem_7rem_auto] sm:items-end">
      <div className="space-y-1.5">
        <Label>Product</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              className="w-full justify-between font-normal"
              disabled={disabled}
            >
              <span className={cn("truncate", !product && "text-muted-foreground")}>
                {product ? product.name : "Search the catalog"}
              </span>
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
            <Command>
              <CommandInput placeholder="Search products…" />
              <CommandList>
                <CommandEmpty>No product matches.</CommandEmpty>
                {grouped.map(([category, items]) => (
                  <CommandGroup key={category} heading={category}>
                    {items.map((item) => (
                      <CommandItem
                        key={item.id}
                        value={`${item.name} ${item.category}`}
                        onSelect={() => pick(item.id)}
                      >
                        <CheckIcon
                          className={cn(
                            "size-4",
                            item.id === productId ? "opacity-100" : "opacity-0"
                          )}
                        />
                        <span className="truncate">{item.name}</span>
                        {item.is_subscription ? (
                          <span className="ml-auto text-xs text-muted-foreground">
                            {item.recurring_interval}
                          </span>
                        ) : null}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ))}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      <div className="space-y-1.5">
        <Label>Variant</Label>
        {variants.length > 1 ? (
          <Select value={variantId} onValueChange={setVariantId} disabled={disabled}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Choose a variant" />
            </SelectTrigger>
            <SelectContent>
              {variants.map((variant) => (
                <SelectItem key={variant.id} value={variant.id}>
                  {variant.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            readOnly
            disabled
            value={chosenVariant?.sku ?? "—"}
            className="font-mono text-xs"
          />
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Qty</Label>
        <Input
          type="number"
          min={1}
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          disabled={disabled}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Discount %</Label>
        <Input
          type="number"
          min={0}
          max={100}
          step="0.5"
          value={discount}
          onChange={(event) => setDiscount(event.target.value)}
          disabled={disabled}
        />
      </div>

      <Button onClick={submit} disabled={disabled || !chosenVariant}>
        <PlusIcon /> Add line
      </Button>
    </div>
  )
}
