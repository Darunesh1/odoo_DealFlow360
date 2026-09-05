import { Link } from "react-router-dom"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { money, relativeTime, statusTone } from "@/features/quotations/format"
import { useMyQuotations } from "@/features/portal/use-portal"
import { QUOTATION_STAGE_LABELS } from "@/types/api"

export default function PortalQuotationsPage() {
  const { data, isLoading } = useMyQuotations()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Your account"
        title="My quotations"
        description="Review, ask questions, propose different terms, or confirm — all here."
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (data ?? []).length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm font-medium">Nothing to review yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              When your account manager sends you a quotation, it appears here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {(data ?? []).map((row) => (
            <Link key={row.id} to={`/portal/quotations/${row.id}`}>
              <Card className="transition-colors hover:border-foreground/25">
                <CardContent className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="font-mono text-xs text-muted-foreground">
                      {row.number}
                    </p>
                    <p className="font-mono text-2xl tabular-nums">
                      {money(row.total, row.currency)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Updated {relativeTime(row.updated_at)}
                      {row.valid_until
                        ? ` · valid until ${new Date(row.valid_until).toLocaleDateString()}`
                        : ""}
                    </p>
                  </div>
                  <Badge variant={statusTone(row.status)}>
                    {QUOTATION_STAGE_LABELS[row.status]}
                  </Badge>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
