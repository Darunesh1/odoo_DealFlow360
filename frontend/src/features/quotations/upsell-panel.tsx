import {
  ArrowUpCircleIcon,
  PlusIcon,
  SparklesIcon,
  TrendingUpIcon,
  XIcon,
} from "lucide-react"

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
  onUpgrade,
}: {
  suggestions: UpsellSuggestion[]
  currency: string
  isLoading: boolean
  disabled: boolean
  onAdd: (suggestion: UpsellSuggestion) => void
  onDismiss: (suggestion: UpsellSuggestion) => void
  onUpgrade: (suggestion: UpsellSuggestion) => void
}) {
  // Two different questions: "which one?" and "what else?". Grouped rather than
  // interleaved, because an upgrade replaces a line the rep already chose while
  // a cross-sell adds one, and a card that does not say which is a trap.
  const upsells = suggestions.filter((item) => item.kind === "upsell")
  const crossSells = suggestions.filter((item) => item.kind !== "upsell")
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SparklesIcon className="size-4 text-brass" />
          Upsell &amp; cross-sell
        </CardTitle>
        <CardDescription>
          Upgrades to what is on the quote, then what sells alongside it -
          ranked on co-purchase history, pairings, promotions and margin.
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
          [...upsells, ...crossSells].map((suggestion) => (
            <div
              key={`${suggestion.kind}:${suggestion.variant_id}`}
              className="group rounded-lg border p-3 transition-colors hover:border-foreground/25"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  {suggestion.kind === "upsell" ? (
                    <p className="mb-0.5 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-brass">
                      <ArrowUpCircleIcon className="size-3" /> Upgrade
                      {suggestion.price_delta != null
                        ? ` · +${money(suggestion.price_delta, currency)}`
                        : ""}
                    </p>
                  ) : null}
                  <p className="truncate text-sm font-medium">{suggestion.name}</p>
                  <p className="text-xs text-muted-foreground">{suggestion.reason}</p>
                  {suggestion.rationale ? (
                    // Kept visually distinct from `reason` above it: that one is
                    // provenance the catalogue vouches for, this one is a model's
                    // opinion about this particular deal.
                    <p className="mt-1 flex items-start gap-1 text-xs italic text-muted-foreground">
                      <SparklesIcon className="mt-0.5 size-3 shrink-0 text-brass" />
                      <span>{suggestion.rationale}</span>
                    </p>
                  ) : null}
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
                {suggestion.kind === "upsell" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7"
                    disabled={disabled}
                    onClick={() => onUpgrade(suggestion)}
                  >
                    <ArrowUpCircleIcon /> Upgrade the line
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7"
                    disabled={disabled}
                    onClick={() => onAdd(suggestion)}
                  >
                    <PlusIcon /> Add to quote
                  </Button>
                )}
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
