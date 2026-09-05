import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  ArrowLeftIcon,
  CheckIcon,
  ExternalLinkIcon,
  MergeIcon,
  PencilIcon,
  TruckIcon,
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
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/features/auth/use-auth"
import {
  useFulfillment,
  useFulfillmentActions,
} from "@/features/fulfillment/use-fulfillment"
import { money } from "@/features/quotations/format"
import { api } from "@/lib/api"
import { useQuery } from "@tanstack/react-query"
import { cn } from "@/lib/utils"
import {
  FULFILLMENT_STATUS_LABELS,
  type Allocation,
  type OverrideRowInput,
  type Warehouse,
} from "@/types/api"

const ALLOCATION_TONE: Record<string, string> = {
  planned: "bg-muted text-muted-foreground",
  reserved: "bg-sky-500/15 text-sky-700 dark:text-sky-400",
  backordered: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  partially_shipped: "bg-sky-500/15 text-sky-700 dark:text-sky-400",
  shipped: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
  cancelled: "bg-muted text-muted-foreground",
}

export default function FulfillmentDetailPage() {
  const { fulfillmentId } = useParams<{ fulfillmentId: string }>()
  const { hasRole } = useAuth()
  const canOperate = hasRole("admin", "finance")

  const { data: fulfillment, isLoading } = useFulfillment(fulfillmentId)
  const actions = useFulfillmentActions(fulfillmentId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<OverrideRowInput[]>([])

  const { data: warehouses } = useQuery({
    queryKey: ["lookups", "warehouses"],
    queryFn: async () => (await api.get<Warehouse[]>("/lookups/warehouses")).data,
    staleTime: 300_000,
  })

  const shippedUnits = useMemo(
    () => (fulfillment?.allocations ?? []).reduce((sum, a) => sum + a.quantity_shipped, 0),
    [fulfillment]
  )

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading the split…</p>
  }
  if (!fulfillment) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          That fulfillment does not exist.
        </CardContent>
      </Card>
    )
  }

  const accepted = Boolean(fulfillment.accepted_at)

  const startEditing = () => {
    setDraft(
      fulfillment.allocations.map((allocation) => ({
        quotation_line_id: allocation.quotation_line_id,
        warehouse_id: allocation.warehouse_id,
        quantity: allocation.quantity,
        status: allocation.status === "backordered" ? "backordered" : undefined,
      }))
    )
    setEditing(true)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <Link
            to="/app/fulfillment"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <ArrowLeftIcon className="size-3" /> Fulfillment
          </Link>
        }
        title={`${fulfillment.quotation_number} · ${fulfillment.customer_name}`}
        description="The recommended warehouse split for this order, based on live stock."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to={`/app/quotations/${fulfillment.quotation_id}`}>
              <ExternalLinkIcon /> Open quotation
            </Link>
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={fulfillment.has_backorder ? "destructive" : "secondary"}>
          {FULFILLMENT_STATUS_LABELS[fulfillment.status]}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {fulfillment.strategy === "manual_override"
            ? "Overridden by hand"
            : "Suggested by the planner"}
        </span>
        <span className="text-sm text-muted-foreground">
          · {fulfillment.estimated_shipment_count} shipment
          {fulfillment.estimated_shipment_count === 1 ? "" : "s"}
        </span>
        <span className="text-sm text-muted-foreground">
          · {money(fulfillment.estimated_shipping_cost, fulfillment.currency)} estimated
        </span>
        {shippedUnits > 0 ? (
          <span className="text-sm text-muted-foreground">
            · {shippedUnits} units shipped
          </span>
        ) : null}
      </div>

      {fulfillment.can_consolidate ? (
        <Card className="border-amber-500/40 bg-amber-500/[0.04]">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <p className="text-sm font-medium">Stock has arrived for a backorder</p>
              <p className="text-sm text-muted-foreground">
                It can be reserved and folded into the shipment already planned
                for that warehouse, rather than opening a second one.
              </p>
            </div>
            {canOperate ? (
              <Button
                size="sm"
                onClick={() => actions.consolidate.mutate()}
                disabled={actions.consolidate.isPending}
              >
                <MergeIcon /> Consolidate remaining backorder
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Warehouse split</CardTitle>
              <CardDescription>
                Fewest warehouses first, ties broken on the shipping rates an
                admin entered. Anything no warehouse can cover backorders.
              </CardDescription>
            </div>
            {canOperate && !accepted ? (
              <div className="flex gap-2">
                {editing ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditing(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() =>
                        actions.override.mutate(draft, {
                          onSuccess: () => setEditing(false),
                        })
                      }
                      disabled={actions.override.isPending}
                    >
                      Save override
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={startEditing}>
                      <PencilIcon /> Manual override
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => actions.accept.mutate()}
                      disabled={actions.accept.isPending}
                    >
                      <CheckIcon /> Accept suggested split
                    </Button>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[14rem]">Line</TableHead>
                  <TableHead className="min-w-[12rem]">Warehouse</TableHead>
                  <TableHead className="text-right">Qty fulfilled</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Est. cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fulfillment.allocations.map((allocation, index) => (
                  <AllocationRow
                    key={allocation.id}
                    allocation={allocation}
                    currency={fulfillment.currency}
                    editing={editing}
                    warehouses={warehouses ?? []}
                    draft={draft[index]}
                    onDraftChange={(next) =>
                      setDraft((current) =>
                        current.map((row, i) => (i === index ? next : row))
                      )
                    }
                  />
                ))}
              </TableBody>
            </Table>
          </div>
          {editing ? (
            <p className="border-t px-6 pt-4 text-sm text-muted-foreground">
              Every line&apos;s quantities must still add up to what was sold, and
              no warehouse may be drawn below what it holds — the server refuses
              the batch otherwise.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Shipments</CardTitle>
          <CardDescription>
            A shipment exists as a planned row from the moment the split is
            accepted, so the estimate and the reality are the same rows in two
            states. Shipping is what makes units billable.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {fulfillment.shipments.length === 0 ? (
            <p className="px-6 py-8 text-center text-sm text-muted-foreground">
              None yet — accept the split first.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Reference</TableHead>
                    <TableHead>Warehouse</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Units</TableHead>
                    <TableHead className="text-right">Est. cost</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fulfillment.shipments.map((shipment) => (
                    <TableRow key={shipment.id}>
                      <TableCell className="font-mono text-xs">
                        {shipment.reference}
                      </TableCell>
                      <TableCell>{shipment.warehouse_name}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            shipment.status === "shipped" ||
                            shipment.status === "delivered"
                              ? "default"
                              : "outline"
                          }
                        >
                          {shipment.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {shipment.unit_count}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {money(shipment.estimated_cost, fulfillment.currency)}
                      </TableCell>
                      <TableCell className="text-right">
                        {canOperate && shipment.status === "planned" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7"
                            onClick={() => actions.ship.mutate(shipment.id)}
                            disabled={actions.ship.isPending}
                          >
                            <TruckIcon /> Ship
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function AllocationRow({
  allocation,
  currency,
  editing,
  warehouses,
  draft,
  onDraftChange,
}: {
  allocation: Allocation
  currency: string
  editing: boolean
  warehouses: Warehouse[]
  draft?: OverrideRowInput
  onDraftChange: (next: OverrideRowInput) => void
}) {
  return (
    <TableRow>
      <TableCell>
        <p className="font-medium leading-tight">{allocation.line_label}</p>
        {allocation.sku ? (
          <p className="font-mono text-xs text-muted-foreground">{allocation.sku}</p>
        ) : null}
      </TableCell>

      <TableCell>
        {editing && draft ? (
          <Select
            value={draft.warehouse_id}
            onValueChange={(value) => onDraftChange({ ...draft, warehouse_id: value })}
          >
            <SelectTrigger className="h-8 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {warehouses.map((warehouse) => (
                <SelectItem key={warehouse.id} value={warehouse.id}>
                  {warehouse.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          allocation.warehouse_name
        )}
      </TableCell>

      <TableCell className="text-right">
        {editing && draft ? (
          <Input
            type="number"
            min={1}
            value={draft.quantity}
            onChange={(event) =>
              onDraftChange({ ...draft, quantity: Number(event.target.value) || 1 })
            }
            className="h-8 w-20 text-right font-mono tabular-nums"
          />
        ) : (
          <span className="font-mono tabular-nums">{allocation.quantity} units</span>
        )}
      </TableCell>

      <TableCell>
        <span
          className={cn(
            "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
            ALLOCATION_TONE[allocation.status]
          )}
        >
          {allocation.status.replace("_", " ")}
        </span>
        {allocation.expected_restock_date ? (
          <p className="mt-0.5 text-xs text-muted-foreground">
            expected {new Date(allocation.expected_restock_date).toLocaleDateString()}
          </p>
        ) : null}
      </TableCell>

      <TableCell className="text-right font-mono tabular-nums">
        {money(allocation.estimated_shipping_cost, currency)}
      </TableCell>
    </TableRow>
  )
}
