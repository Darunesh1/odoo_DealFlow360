import { Link } from "react-router-dom"
import { ListIcon } from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { money, relativeTime } from "@/features/quotations/format"
import { RiskBadge } from "@/features/quotations/risk-badge"
import { usePipeline } from "@/features/quotations/use-quotation"
import { PIPELINE_STAGES, QUOTATION_STAGE_LABELS } from "@/types/api"

/**
 * Spec B2: the Kanban deal pipeline.
 *
 * Read-only columns rather than drag-and-drop. A quotation's stage is decided
 * by the approval chain and the fulfillment flow, so dragging a card between
 * columns would either lie about what happened or silently bypass an approval.
 */
export default function PipelinePage() {
  const { data, isLoading } = usePipeline()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Sales"
        title="Pipeline"
        description="Every open deal by stage. A card moves when its approval or fulfillment moves, not by hand."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to="/app/quotations">
              <ListIcon /> List view
            </Link>
          </Button>
        }
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading the board…</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {PIPELINE_STAGES.map((stage) => {
            const cards = data?.[stage] ?? []
            return (
              <div key={stage} className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-medium">
                    {QUOTATION_STAGE_LABELS[stage]}
                  </h2>
                  <span className="rounded-full bg-muted px-1.5 py-px font-mono text-[10px] tabular-nums text-muted-foreground">
                    {cards.length}
                  </span>
                </div>

                <div className="space-y-2">
                  {cards.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                      Nothing here
                    </div>
                  ) : (
                    cards.map((card) => (
                      <Link key={card.id} to={`/app/quotations/${card.id}`}>
                        <Card className="transition-colors hover:border-foreground/25">
                          <CardContent className="space-y-2 py-3">
                            <p className="truncate text-sm font-medium">
                              {card.customer_name}
                            </p>
                            <p className="font-mono text-lg tabular-nums">
                              {money(card.total, card.currency)}
                            </p>
                            <div className="flex flex-wrap items-center gap-1.5">
                              <RiskBadge band={card.risk_band} />
                              <span className="text-xs text-muted-foreground">
                                {relativeTime(
                                  card.last_activity_at ?? card.updated_at
                                )}
                              </span>
                            </div>
                          </CardContent>
                        </Card>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
