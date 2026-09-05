import { useEffect, useRef, useState } from "react"
import { MinusIcon, PlusIcon, Trash2Icon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { TableCell, TableRow } from "@/components/ui/table"
import { money } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import type { QuotationLine } from "@/types/api"

const AUTOSAVE_MS = 400

/**
 * One order line.
 *
 * Quantity and discount autosave rather than waiting for a Save button: the
 * whole point of the screen is that a rep sees the line flip to OVER as they
 * type, and a button between the typing and the answer defeats that. The debounce
 * is what stops a held-down stepper firing eight requests.
 */
export function LineRow({
  line,
  currency,
  editable,
  onChange,
  onRemove,
}: {
  line: QuotationLine
  currency: string
  editable: boolean
  onChange: (body: { quantity?: number; line_discount_percent?: number }) => void
  onRemove: () => void
}) {
  const [quantity, setQuantity] = useState(String(line.quantity))
  const [discount, setDiscount] = useState(String(line.line_discount_percent))
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Tracks whether this row has pending local edits, so a server response
  // arriving mid-typing does not yank the cursor back.
  const dirty = useRef(false)

  useEffect(() => {
    if (dirty.current) return
    setQuantity(String(line.quantity))
    setDiscount(String(line.line_discount_percent))
  }, [line.quantity, line.line_discount_percent])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    []
  )

  const queue = (next: { quantity?: string; discount?: string }) => {
    dirty.current = true
    if (next.quantity !== undefined) setQuantity(next.quantity)
    if (next.discount !== undefined) setDiscount(next.discount)

    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const q = Math.max(1, Number(next.quantity ?? quantity) || 1)
      const d = Math.min(100, Math.max(0, Number(next.discount ?? discount) || 0))
      dirty.current = false
      onChange({ quantity: q, line_discount_percent: d })
    }, AUTOSAVE_MS)
  }

  const step = (delta: number) =>
    queue({ quantity: String(Math.max(1, (Number(quantity) || 1) + delta)) })

  const over = line.over_by_points > 0
  const shortStock =
    line.stock_available_at_entry !== null &&
    line.stock_available_at_entry < line.quantity

  return (
    <TableRow className={cn(over && "bg-red-500/[0.04]")}>
      <TableCell className="min-w-[14rem]">
        <p className="font-medium leading-tight">{line.product_name}</p>
        <p className="font-mono text-xs text-muted-foreground">
          {line.sku ?? "—"}
          {line.variant_name && line.variant_name !== "Default"
            ? ` · ${line.variant_name}`
            : ""}
        </p>
        {shortStock ? (
          <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
            Only {line.stock_available_at_entry} in stock — the rest backorders
          </p>
        ) : null}
      </TableCell>

      <TableCell className="min-w-[9rem]">
        {editable ? (
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="size-7 shrink-0 p-0"
              onClick={() => step(-1)}
              disabled={Number(quantity) <= 1}
              aria-label="Decrease quantity"
            >
              <MinusIcon className="size-3" />
            </Button>
            <Input
              type="number"
              min={1}
              value={quantity}
              onChange={(event) => queue({ quantity: event.target.value })}
              className="h-7 w-14 px-1 text-center font-mono tabular-nums"
            />
            <Button
              variant="outline"
              size="sm"
              className="size-7 shrink-0 p-0"
              onClick={() => step(1)}
              aria-label="Increase quantity"
            >
              <PlusIcon className="size-3" />
            </Button>
          </div>
        ) : (
          <span className="font-mono tabular-nums">{line.quantity}</span>
        )}
      </TableCell>

      <TableCell className="text-right font-mono tabular-nums">
        {money(line.unit_price, currency)}
      </TableCell>

      <TableCell className="min-w-[6rem]">
        {editable ? (
          <Input
            type="number"
            min={0}
            max={100}
            step="0.5"
            value={discount}
            onChange={(event) => queue({ discount: event.target.value })}
            className="h-7 w-20 text-right font-mono tabular-nums"
          />
        ) : (
          <span className="font-mono tabular-nums">{line.line_discount_percent}%</span>
        )}
      </TableCell>

      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
        {line.allowed_discount_percent >= 100
          ? "—"
          : `${line.allowed_discount_percent}%`}
      </TableCell>

      <TableCell>
        {over ? (
          <span className="inline-flex items-center rounded-md border border-transparent bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-400">
            OVER +{line.over_by_points}pt
          </span>
        ) : (
          <span className="inline-flex items-center rounded-md border border-transparent bg-emerald-500/12 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
            OK
          </span>
        )}
      </TableCell>

      <TableCell className="text-right font-mono tabular-nums">
        {money(line.line_total, currency)}
      </TableCell>

      <TableCell className="w-10">
        {editable ? (
          <Button
            variant="ghost"
            size="sm"
            className="size-7 p-0 text-muted-foreground hover:text-destructive"
            onClick={onRemove}
            aria-label={`Remove ${line.product_name}`}
          >
            <Trash2Icon className="size-3.5" />
          </Button>
        ) : null}
      </TableCell>
    </TableRow>
  )
}
