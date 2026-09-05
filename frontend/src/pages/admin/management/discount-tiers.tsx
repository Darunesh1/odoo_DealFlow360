import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, Trash2Icon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { SortableHeader } from "@/components/sortable-header"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useTableSort } from "@/hooks/use-table-sort"
import { api, errorMessage } from "@/lib/api"
import type { CategoryLimit, CustomerTier } from "@/types/api"

interface ApprovalRuleStep {
  step_order: number
  role: string
}

interface ApprovalRule {
  id: string
  name: string
  risk_band: string
  steps: ApprovalRuleStep[]
}

const ROLE_LABEL: Record<string, string> = {
  sales_manager: "Sales Manager",
  finance: "Finance",
}

/** Screen 18's third panel: what a discount range routes to. */
function chainLabel(rule: ApprovalRule) {
  if (!rule.steps.length) return "No approval needed"
  return rule.steps
    .slice()
    .sort((a, b) => a.step_order - b.step_order)
    .map((step) => ROLE_LABEL[step.role] ?? step.role)
    .join(" then ")
}

export default function DiscountTiersTab() {
  const queryClient = useQueryClient()

  const [tierName, setTierName] = useState("")
  const [tierDiscount, setTierDiscount] = useState("")
  const [categoryName, setCategoryName] = useState("")
  const [categoryDiscount, setCategoryDiscount] = useState("")

  const tiersQuery = useQuery({
    queryKey: ["admin", "customer-tiers"],
    queryFn: async () => (await api.get<CustomerTier[]>("/admin/customer-tiers")).data,
  })
  const limitsQuery = useQuery({
    queryKey: ["admin", "category-limits"],
    queryFn: async () => (await api.get<CategoryLimit[]>("/admin/category-limits")).data,
  })
  const rulesQuery = useQuery({
    queryKey: ["admin", "approval-rules"],
    queryFn: async () => (await api.get<ApprovalRule[]>("/admin/approval-rules")).data,
  })

  const tiers = tiersQuery.data ?? []
  const limits = limitsQuery.data ?? []
  const rules = rulesQuery.data ?? []

  // Tiers arrive ordered by ceiling; sorting by name is the other view worth having.
  const tierSort = useTableSort(tiers, "max_discount_percent")
  const limitSort = useTableSort(limits, "category")

  const refreshTiers = () =>
    queryClient.invalidateQueries({ queryKey: ["admin", "customer-tiers"] })
  const refreshLimits = () =>
    queryClient.invalidateQueries({ queryKey: ["admin", "category-limits"] })

  const createTier = useMutation({
    mutationFn: async () =>
      (
        await api.post<CustomerTier>("/admin/customer-tiers", {
          name: tierName.trim(),
          max_discount_percent: Number(tierDiscount) || 0,
        })
      ).data,
    onSuccess: async () => {
      setTierName("")
      setTierDiscount("")
      await refreshTiers()
      toast.success("Tier added.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not add the tier.")),
  })

  const updateTier = useMutation({
    mutationFn: async ({ id, value }: { id: string; value: number }) =>
      (await api.patch<CustomerTier>(`/admin/customer-tiers/${id}`, {
        max_discount_percent: value,
      })).data,
    onSuccess: async () => {
      await refreshTiers()
      toast.success("Ceiling saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the ceiling.")),
  })

  const deleteTier = useMutation({
    mutationFn: async (id: string) => api.delete(`/admin/customer-tiers/${id}`),
    onSuccess: async () => {
      await refreshTiers()
      toast.success("Tier deleted.")
    },
    // A 409 here is the in-use guard, and its detail names what is blocking.
    onError: (caught) => toast.error(errorMessage(caught, "Could not delete the tier.")),
  })

  const createLimit = useMutation({
    mutationFn: async () =>
      (
        await api.post<CategoryLimit>("/admin/category-limits", {
          category: categoryName.trim(),
          max_discount_percent: Number(categoryDiscount) || 0,
        })
      ).data,
    onSuccess: async () => {
      setCategoryName("")
      setCategoryDiscount("")
      await refreshLimits()
      toast.success("Category ceiling added.")
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not add the category ceiling.")),
  })

  const updateLimit = useMutation({
    mutationFn: async ({ id, value }: { id: string; value: number }) =>
      (await api.patch<CategoryLimit>(`/admin/category-limits/${id}`, {
        max_discount_percent: value,
      })).data,
    onSuccess: async () => {
      await refreshLimits()
      toast.success("Ceiling saved.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not save the ceiling.")),
  })

  const deleteLimit = useMutation({
    mutationFn: async (id: string) => api.delete(`/admin/category-limits/${id}`),
    onSuccess: async () => {
      await refreshLimits()
      toast.success("Category ceiling removed. That category is now uncapped.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not remove the ceiling.")),
  })

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tier Discount Ceilings</CardTitle>
            <CardDescription>
              Does two jobs: the discount already baked into that tier&apos;s prices, and
              the ceiling a rep may discount further before a line is flagged. Changing
              it reprices the catalog.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHeader
                    column="name"
                    active={tierSort.sortKey}
                    direction={tierSort.direction}
                    onSort={tierSort.toggle}
                    className="min-w-[12rem]"
                  >
                    Tier
                  </SortableHeader>
                  <SortableHeader
                    column="max_discount_percent"
                    active={tierSort.sortKey}
                    direction={tierSort.direction}
                    onSort={tierSort.toggle}
                    className="min-w-[10rem]"
                  >
                    Max Discount
                  </SortableHeader>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {tierSort.sorted.map((tier) => (
                  <TableRow key={tier.id}>
                    <TableCell className="font-medium">{tier.name}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        defaultValue={tier.max_discount_percent}
                        className="h-8 w-24"
                        onBlur={(event) => {
                          const value = Number(event.target.value)
                          if (value !== tier.max_discount_percent) {
                            updateTier.mutate({ id: tier.id, value })
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${tier.name}`}
                        onClick={() => deleteTier.mutate(tier.id)}
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {!tiers.length && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-sm text-muted-foreground">
                      No tiers yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className="flex flex-wrap items-end gap-2">
              <Input
                placeholder="Tier name"
                value={tierName}
                onChange={(event) => setTierName(event.target.value)}
                className="w-40"
              />
              <Input
                type="number"
                min="0"
                max="100"
                step="0.01"
                placeholder="Max %"
                value={tierDiscount}
                onChange={(event) => setTierDiscount(event.target.value)}
                className="w-28"
              />
              <Button
                onClick={() => createTier.mutate()}
                disabled={!tierName.trim() || createTier.isPending}
              >
                <PlusIcon className="size-4" />
                Add tier
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Category Discount Ceilings</CardTitle>
            <CardDescription>
              A category listed here is capped even for a generous tier. A category
              that is absent has no ceiling of its own.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHeader
                    column="category"
                    active={limitSort.sortKey}
                    direction={limitSort.direction}
                    onSort={limitSort.toggle}
                    className="min-w-[12rem]"
                  >
                    Category
                  </SortableHeader>
                  <SortableHeader
                    column="max_discount_percent"
                    active={limitSort.sortKey}
                    direction={limitSort.direction}
                    onSort={limitSort.toggle}
                    className="min-w-[10rem]"
                  >
                    Max Discount
                  </SortableHeader>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {limitSort.sorted.map((limit) => (
                  <TableRow key={limit.id}>
                    <TableCell className="font-medium">{limit.category}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        defaultValue={limit.max_discount_percent}
                        className="h-8 w-24"
                        onBlur={(event) => {
                          const value = Number(event.target.value)
                          if (value !== limit.max_discount_percent) {
                            updateLimit.mutate({ id: limit.id, value })
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove the ${limit.category} ceiling`}
                        onClick={() => deleteLimit.mutate(limit.id)}
                      >
                        <Trash2Icon className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {!limits.length && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-sm text-muted-foreground">
                      No category ceilings. Every line is capped by its tier alone.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className="flex flex-wrap items-end gap-2">
              <Input
                placeholder="Category"
                value={categoryName}
                onChange={(event) => setCategoryName(event.target.value)}
                className="w-40"
              />
              <Input
                type="number"
                min="0"
                max="100"
                step="0.01"
                placeholder="Max %"
                value={categoryDiscount}
                onChange={(event) => setCategoryDiscount(event.target.value)}
                className="w-28"
              />
              <Button
                onClick={() => createLimit.mutate()}
                disabled={!categoryName.trim() || createLimit.isPending}
              >
                <PlusIcon className="size-4" />
                Add category
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Approval Routing</CardTitle>
          <CardDescription>
            A quotation is scored against every line's own ceiling. The worst line and
            the pattern across the order together set the blended risk, and that
            decides who reviews it.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Discount range</TableHead>
                <TableHead>Routes to</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>{rule.name}</TableCell>
                  <TableCell>
                    {rule.steps.length ? (
                      chainLabel(rule)
                    ) : (
                      <Badge variant="secondary">No approval needed</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {!rules.length && (
                <TableRow>
                  <TableCell colSpan={2} className="text-sm text-muted-foreground">
                    No approval rules configured.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
