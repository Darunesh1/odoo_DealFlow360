import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
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
import { api } from "@/lib/api"
import type { CustomerTier, Product } from "@/types/api"

export default function SubscriptionPlansTab() {
  const plansQuery = useQuery({
    queryKey: ["admin", "subscription-plans"],
    queryFn: async () => (await api.get<Product[]>("/admin/subscription-plans")).data,
  })
  const tiersQuery = useQuery({
    queryKey: ["admin", "customer-tiers"],
    queryFn: async () => (await api.get<CustomerTier[]>("/admin/customer-tiers")).data,
  })

  const plans = plansQuery.data ?? []
  const tiers = tiersQuery.data ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recurring plans</CardTitle>
        <CardDescription>
          Every product marked as a subscription, with the interval it bills on. Add one
          by creating a product and switching Subscription on.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Plan</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="w-32">Cycle</TableHead>
              <TableHead className="w-24">Tax %</TableHead>
              <TableHead className="w-28">Status</TableHead>
              {tiers.map((tier) => (
                <TableHead key={tier.id} className="w-32 text-right">
                  {tier.name}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {plans.map((plan) => {
              const variant = plan.variants[0]
              return (
                <TableRow key={plan.id}>
                  <TableCell className="font-medium">
                    <Link
                      to={`/app/admin/products/${plan.id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {plan.name}
                    </Link>
                  </TableCell>
                  <TableCell>{plan.category}</TableCell>
                  <TableCell className="capitalize">{plan.recurring_interval}</TableCell>
                  <TableCell>{plan.tax_percent}%</TableCell>
                  <TableCell>
                    <Badge
                      variant={plan.status === "active" ? "secondary" : "outline"}
                      className="capitalize"
                    >
                      {plan.status}
                    </Badge>
                  </TableCell>
                  {tiers.map((tier) => {
                    // The base-currency price is enough here; the full grid
                    // lives on the product form.
                    const price = variant?.prices.find(
                      (item) => item.tier_id === tier.id
                    )
                    return (
                      <TableCell key={tier.id} className="text-right tabular-nums">
                        {price
                          ? `${price.unit_price.toFixed(2)} ${price.currency_code}`
                          : "—"}
                      </TableCell>
                    )
                  })}
                </TableRow>
              )
            })}
            {!plans.length && (
              <TableRow>
                <TableCell colSpan={5 + tiers.length} className="text-sm text-muted-foreground">
                  No recurring plans yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
