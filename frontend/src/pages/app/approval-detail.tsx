import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  ArrowLeftIcon,
  CheckIcon,
  CircleDashedIcon,
  CircleCheckIcon,
  ExternalLinkIcon,
  RotateCcwIcon,
  XIcon,
} from "lucide-react"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  useApproval,
  useApprovalDecision,
} from "@/features/approvals/use-approvals"
import { money, relativeTime } from "@/features/quotations/format"
import { RiskBadge } from "@/features/quotations/risk-badge"
import { cn } from "@/lib/utils"
import { ROLE_LABELS, type ApprovalStepStatus } from "@/types/api"

export default function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>()
  const { data: approval, isLoading } = useApproval(approvalId)
  const decide = useApprovalDecision(approvalId)
  const [note, setNote] = useState("")

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading approval…</p>
  }
  if (!approval) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          That approval does not exist, or is not yours to see.
        </CardContent>
      </Card>
    )
  }

  const flagged = approval.line_snapshots.filter((line) => line.over_by_points > 0)
  const act = (decision: "approve" | "return" | "reject") =>
    decide.mutate({ decision, note: note.trim() || undefined }, {
      onSuccess: () => setNote(""),
    })

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/app/approvals"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> Approvals
          </Link>
        }
        title={`${approval.quotation_number} · ${approval.customer_name}`}
        description={approval.rule_name}
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to={`/app/quotations/${approval.quotation_id}`}>
              <ExternalLinkIcon /> Open quotation
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <RiskBadge band={approval.risk_band} score={approval.blended_risk_score} />
        {approval.customer_tier ? (
          <span className="text-sm text-muted-foreground">
            {approval.customer_tier} tier
          </span>
        ) : null}
        <span className="text-sm text-muted-foreground">
            · Round {approval.round_number}
        </span>
        <span className="text-sm text-muted-foreground">
          · {money(approval.quotation_total, approval.currency)}
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Why this quote was flagged</CardTitle>
              <CardDescription>
                {flagged.length === 0
                  ? "Every line was within its own limit."
                  : "Frozen as at this round, so a later revision cannot rewrite the reason."}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Line</TableHead>
                      <TableHead className="text-right">Discount given</TableHead>
                      <TableHead className="text-right">Limit allowed</TableHead>
                      <TableHead className="text-right">Over by</TableHead>
                      <TableHead className="text-right">Line net</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {approval.line_snapshots.map((line) => (
                      <TableRow
                        key={line.id}
                        className={cn(line.over_by_points > 0 && "bg-red-500/[0.04]")}
                      >
                        <TableCell className="font-medium">{line.line_label}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {line.discount_percent}%
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                          {line.allowed_discount_percent >= 100
                            ? "—"
                            : `${line.allowed_discount_percent}%`}
                        </TableCell>
                        <TableCell className="text-right">
                          {line.over_by_points > 0 ? (
                            <span className="font-mono font-medium tabular-nums text-red-600 dark:text-red-400">
                              {line.over_by_points} pt OVER
                            </span>
                          ) : (
                            <span className="font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                              0 pt — OK
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {money(line.line_net, approval.currency)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <p className="border-t px-6 pt-4 text-sm text-muted-foreground">
                The worst single line and the revenue-weighted pattern across the
                order together set the blended score of{" "}
                <span className="font-mono">{approval.blended_risk_score.toFixed(2)}</span>.
                One bad line is enough to require approval.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Audit trail</CardTitle>
              <CardDescription>
                Every submission, edit and decision, with who and when.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>When</TableHead>
                      <TableHead>Note</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {approval.audit_trail.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-muted-foreground">
                          Nothing recorded yet.
                        </TableCell>
                      </TableRow>
                    ) : (
                      approval.audit_trail.map((entry) => (
                        <TableRow key={entry.id}>
                          <TableCell className="font-medium">
                            {entry.actor_name}
                          </TableCell>
                          <TableCell className="capitalize">
                            {entry.action.replace("_", " ")}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {new Date(entry.created_at).toLocaleString()}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {entry.reason ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Approval chain</CardTitle>
              <CardDescription>
                {approval.steps.length === 0
                  ? "No steps — within every ceiling."
                  : "Sequential: each step waits for the one before it."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3">
                <Step
                  label="Submitted"
                  by={approval.submitted_by_name}
                  when={approval.submitted_at}
                  status="approved"
                />
                {approval.steps.map((step) => (
                  <Step
                    key={step.id}
                    label={ROLE_LABELS[step.role]}
                    by={step.decided_by_name}
                    when={step.decided_at}
                    status={step.status}
                    note={step.note}
                  />
                ))}
                <Step
                  label="Confirmed"
                  status={approval.status === "approved" ? "approved" : "pending"}
                />
              </ol>
            </CardContent>
          </Card>

          {approval.can_act ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Your decision</CardTitle>
                <CardDescription>
                  {approval.current_role
                    ? `This step is waiting on ${ROLE_LABELS[approval.current_role]}.`
                    : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea
                  rows={3}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Reason — required when returning or rejecting."
                />
                <div className="grid gap-2">
                  <Button onClick={() => act("approve")} disabled={decide.isPending}>
                    <CheckIcon /> Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => act("return")}
                    disabled={decide.isPending}
                  >
                    <RotateCcwIcon /> Return for revision
                  </Button>
                  <Button
                    variant="outline"
                    className="text-destructive hover:text-destructive"
                    onClick={() => act("reject")}
                    disabled={decide.isPending}
                  >
                    <XIcon /> Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : approval.status === "pending" ? (
            <Card>
              <CardContent className="py-6 text-center text-sm text-muted-foreground">
                Waiting on{" "}
                {approval.current_role
                  ? ROLE_LABELS[approval.current_role]
                  : "the next approver"}
                .
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Step({
  label,
  by,
  when,
  status,
  note,
}: {
  label: string
  by?: string | null
  when?: string | null
  status: ApprovalStepStatus | "approved" | "pending"
  note?: string | null
}) {
  const done = status === "approved"
  const stalled = status === "returned" || status === "rejected"
  const Icon = done ? CircleCheckIcon : CircleDashedIcon

  return (
    <li className="flex gap-3">
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          done
            ? "text-emerald-600 dark:text-emerald-400"
            : stalled
              ? "text-red-600 dark:text-red-400"
              : "text-muted-foreground"
        )}
      />
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium">{label}</span>
          <Badge variant="outline" className="capitalize">
            {status}
          </Badge>
        </div>
        {by ? (
          <p className="text-xs text-muted-foreground">
            {by}
            {when ? ` · ${relativeTime(when)}` : ""}
          </p>
        ) : null}
        {note ? <p className="text-xs text-muted-foreground">“{note}”</p> : null}
      </div>
    </li>
  )
}
