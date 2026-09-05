import { cn } from "@/lib/utils"
import { RISK_CLASS, RISK_LABEL } from "@/features/quotations/format"
import type { RiskBand } from "@/types/api"

/** The blended risk band, shown wherever a quotation is. */
export function RiskBadge({
  band,
  score,
  className,
}: {
  band: RiskBand
  score?: number
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        RISK_CLASS[band],
        className
      )}
    >
      {RISK_LABEL[band]}
      {score !== undefined && band !== "none" ? (
        <span className="font-mono tabular-nums opacity-70">
          {score.toFixed(1)}
        </span>
      ) : null}
    </span>
  )
}
