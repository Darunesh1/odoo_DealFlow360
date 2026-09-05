import {
  BookOpenIcon,
  LayoutDashboardIcon,
  LayoutGridIcon,
  FileTextIcon,
  GavelIcon,
  TruckIcon,
  RepeatIcon,
  ReceiptIcon,
  TriangleAlertIcon,
  ChartColumnIcon,
  ShieldCheckIcon,
  PackageIcon,
  UsersIcon,
  WarehouseIcon,
} from "lucide-react"
import type { ComponentType } from "react"
import { Link, useLocation } from "react-router-dom"

import { Brand } from "@/components/brand"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { API_DOCS_URL } from "@/config"
import { useAuth } from "@/features/auth/use-auth"

interface NavItem {
  title: string
  url: string
  icon: ComponentType<{ className?: string }>
  excludes?: string[]
  /** Match nested routes too, rather than only the exact path. */
  nested?: boolean
}

const PLATFORM: NavItem[] = [
  { title: "Dashboard", url: "/app", icon: LayoutDashboardIcon },
  { title: "Quotations", url: "/app/quotations", icon: FileTextIcon, nested: true },
  { title: "Pipeline", url: "/app/pipeline", icon: LayoutGridIcon, nested: true },
]

// Every internal role sees approvals; only the waiting step's role can decide.
const GOVERNANCE: NavItem[] = [
  { title: "Approvals", url: "/app/approvals", icon: GavelIcon, nested: true },
  { title: "Fulfillment", url: "/app/fulfillment", icon: TruckIcon, nested: true },
]

const BILLING: NavItem[] = [
  { title: "Subscriptions", url: "/app/subscriptions", icon: RepeatIcon, nested: true },
  { title: "Invoices", url: "/app/invoices", icon: ReceiptIcon, nested: true },
]

const INSIGHT: NavItem[] = [
  { title: "Deal Health", url: "/app/deal-health", icon: TriangleAlertIcon, nested: true },
  { title: "Reports", url: "/app/reports", icon: ChartColumnIcon, nested: true },
]

// Shown to the roles that are NOT admins: an admin reaches the same screens
// through Admin Management, and two identical rows in one sidebar is noise.
const CATALOG: NavItem[] = [
  { title: "Products", url: "/app/products", icon: PackageIcon, nested: true },
]

const OPERATIONS: NavItem[] = [
  { title: "Warehouses", url: "/app/warehouses", icon: WarehouseIcon, nested: true },
]

const ADMINISTRATION: NavItem[] = [
  {
    title: "Admin Management",
    url: "/app/admin",
    icon: PackageIcon,
    nested: true,
    // Users lives under /app/admin too, but is its own entry: without this
    // both rows would highlight at once.
    excludes: ["/app/admin/users"],
  },
  { title: "Users", url: "/app/admin/users", icon: UsersIcon, nested: true },
]

export function AppSidebar() {
  const { isAdmin, hasRole } = useAuth()
  const { pathname } = useLocation()
  const canSeeSales = hasRole("admin", "sales_rep", "sales_manager")
  const canSeeApprovals = hasRole("admin", "sales_rep", "sales_manager", "finance")
  // Catalog and warehouse entries are for non-admins only: an admin gets the
  // same screens as tabs inside Admin Management.
  const canSeeCatalog = !isAdmin && hasRole("sales_rep", "sales_manager", "finance")
  const canManageWarehouses = !isAdmin && hasRole("finance")

  const isActive = (item: NavItem) =>
    item.nested
      ? pathname.startsWith(item.url) &&
        !(item.excludes ?? []).some((path) => pathname.startsWith(path))
      : pathname === item.url

  const renderGroup = (label: string, items: NavItem[]) => (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.url}>
              <SidebarMenuButton asChild isActive={isActive(item)} tooltip={item.title}>
                <Link to={item.url}>
                  <item.icon className="size-4" />
                  <span>{item.title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 justify-center border-b px-3 group-data-[collapsible=icon]:px-1.5">
        <Brand to="/app" className="group-data-[collapsible=icon]:justify-center" />
      </SidebarHeader>

      <SidebarContent>
        {canSeeSales && renderGroup("Sales Operations", PLATFORM)}
        {canSeeApprovals && renderGroup("Governance", GOVERNANCE)}
        {canSeeApprovals && renderGroup("Billing", BILLING)}
        {canSeeApprovals && renderGroup("Insight", INSIGHT)}
        {canSeeCatalog && renderGroup("Catalog", CATALOG)}
        {canManageWarehouses && renderGroup("Operations", OPERATIONS)}
        {isAdmin && renderGroup("Administration", ADMINISTRATION)}

        <SidebarGroup className="mt-auto">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="API reference">
                  <a href={API_DOCS_URL} target="_blank" rel="noreferrer">
                    <BookOpenIcon className="size-4" />
                    <span>API reference</span>
                  </a>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {isAdmin && (
                <SidebarMenuItem>
                  <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                    <ShieldCheckIcon className="size-3.5 text-brass" />
                    Signed in as an administrator
                  </div>
                </SidebarMenuItem>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t">
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
