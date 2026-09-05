import { TrendingDownIcon, TrendingUpIcon } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { money } from "@/features/quotations/format"
import { cn } from "@/lib/utils"
import type { Quotation } from "@/types/api"

/**
 * The live margin indicator the spec keeps asking for (B3, B5).
 *
 * Margin is shown as an amount and a percentage of the total, because a
 * $200 margin means something different on a $500 deal than on a $50,000 one,
 * and that is exactly the judgement a rep is making when they take a discount.
 */
export function TotalsBar({ quotation }: { quotation: Quotation }) {
  const marginPercent = quotation.total
    ? (quotation.margin_total / quotation.total) * 100
    : 0
  const thin = marginPercent < 15

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Figure label="Subtotal" value={money(quotation.subtotal, quotation.currency)} />
      <Figure
        label="Discount"
        value={`− ${money(quotation.discount_total, quotation.currency)}`}
      />
      <Figure
        label="Total"
        value={money(quotation.total, quotation.currency)}
        emphasis
      />
      <Card>
        <CardContent className="space-y-1">
          <p className="label-mono text-muted-foreground">Margin</p>
          <p
            className={cn(
              "flex items-center gap-1.5 font-mono text-xl tabular-nums",
              thin ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {thin ? (
              <TrendingDownIcon className="size-4" />
            ) : (
              <TrendingUpIcon className="size-4" />
            )}
            {money(quotation.margin_total, quotation.currency)}
          </p>
          <p className="text-xs text-muted-foreground">
            {marginPercent.toFixed(1)}% of the total
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function Figure({
  label,
  value,
  emphasis,
}: {
  label: string
  value: string
  emphasis?: boolean
}) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="label-mono text-muted-foreground">{label}</p>
        <p
          className={cn(
            "font-mono tabular-nums",
            emphasis ? "text-xl font-medium" : "text-xl"
          )}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}
