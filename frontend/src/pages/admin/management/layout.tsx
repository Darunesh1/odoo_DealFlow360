import { NavLink, Outlet } from "react-router-dom"

import { PageHeader } from "@/components/page-header"
import { cn } from "@/lib/utils"

const TABS = [
  { to: "/app/admin/products", label: "Products" },
  { to: "/app/admin/price-lists", label: "Price Lists" },
  { to: "/app/admin/discount-tiers", label: "Discount Tiers" },
  { to: "/app/admin/warehouses", label: "Warehouses" },
  { to: "/app/admin/subscription-plans", label: "Subscription Plans" },
]

export default function AdminManagementLayout() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin Management"
        description="Backend configuration: products, pricing, discount ceilings, warehouses and recurring plans."
      />

      <nav className="flex flex-wrap gap-1 border-b">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
