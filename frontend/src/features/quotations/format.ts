import type { QuotationStatus, RiskBand } from "@/types/api"

/** Currency-aware money, used by every screen that shows a total. */
export function money(value: number, currency = "USD") {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value)
}

export function percent(value: number) {
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 2)}%`
}

/** "3 days ago" for the idle-deal indicator, without pulling in a date library. */
export function relativeTime(iso: string | null) {
  if (!iso) return "—"
  const then = new Date(iso).getTime()
  const days = Math.floor((Date.now() - then) / 86_400_000)
  if (days <= 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days} days ago`
  return new Date(iso).toLocaleDateString()
}

type BadgeTone = "default" | "secondary" | "destructive" | "outline"

export function statusTone(status: QuotationStatus): BadgeTone {
  switch (status) {
    case "confirmed":
    case "approved":
      return "default"
    case "rejected":
    case "cancelled":
      return "destructive"
    case "pending_approval":
    case "negotiation":
      return "secondary"
    default:
      return "outline"
  }
}

/**
 * Risk colours. Deliberately not the badge variants: a HIGH band has to read
 * as a warning even next to a destructive "Rejected" badge.
 */
export const RISK_CLASS: Record<RiskBand, string> = {
  none: "border-transparent bg-muted text-muted-foreground",
  low: "border-transparent bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
  medium: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  high: "border-transparent bg-red-500/15 text-red-700 dark:text-red-400",
}

export const RISK_LABEL: Record<RiskBand, string> = {
  none: "No risk",
  low: "Low",
  medium: "Medium",
  high: "High",
}
