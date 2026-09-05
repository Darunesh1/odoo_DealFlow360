import { PlusIcon, SparklesIcon, TrendingUpIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { money } from "@/features/quotations/format"
import type { UpsellSuggestion } from "@/types/api"

/**
 * Spec B5: the ranked suggestion panel that sits beside the cart.
 *
 * The margin delta is not decoration - it is the number the backend already
 * used to decide whether the suggestion was healthy enough to show at all, so
 * showing it is what makes the ranking legible rather than magic.
 */
export function UpsellPanel({
  suggestions,
  currency,
  isLoading,
  disabled,
  onAdd,
  onDismiss,
}: {
  suggestions: UpsellSuggestion[]
  currency: string
  isLoading: boolean
  disabled: boolean
  onAdd: (suggestion: UpsellSuggestion) => void
  onDismiss: (suggestion: UpsellSuggestion) => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SparklesIcon className="size-4 text-brass" />
          Upsell &amp; cross-sell
        </CardTitle>
        <CardDescription>
          Ranked by what sells alongside this cart, what is promoted, and the
          margin each would add.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Looking for suggestions…</p>
        ) : suggestions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing to suggest yet. Add a product and the panel fills in.
          </p>
        ) : (
          suggestions.map((suggestion) => (
            <div
              key={suggestion.product_id}
              className="group rounded-lg border p-3 transition-colors hover:border-foreground/25"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{suggestion.name}</p>
                  <p className="text-xs text-muted-foreground">{suggestion.reason}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 opacity-0 transition-opacity group-hover:opacity-100"
                  onClick={() => onDismiss(suggestion)}
                  aria-label={`Dismiss ${suggestion.name}`}
                >
                  <XIcon className="size-3.5" />
                </Button>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {suggestion.is_promoted && suggestion.promotion_label ? (
                  <Badge className="bg-brass text-brass-foreground hover:bg-brass">
                    {suggestion.promotion_label}
                  </Badge>
                ) : null}
                {suggestion.is_recurring ? (
                  <Badge variant="outline">Recurring</Badge>
                ) : null}
                <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                  <TrendingUpIcon className="size-3" />
                  Margin +{money(suggestion.margin_delta, currency)}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between">
                <span className="font-mono text-sm tabular-nums">
                  {money(suggestion.unit_price, currency)}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7"
                  disabled={disabled}
                  onClick={() => onAdd(suggestion)}
                >
                  <PlusIcon /> Add to quote
                </Button>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
