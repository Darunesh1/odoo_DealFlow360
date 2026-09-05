import {
  BookOpenIcon,
  LayoutDashboardIcon,
  SettingsIcon,
  ShieldCheckIcon,
  UserRoundIcon,
  UsersIcon,
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
  /** Match nested routes too, rather than only the exact path. */
  nested?: boolean
}

const PLATFORM: NavItem[] = [
  { title: "Dashboard", url: "/app", icon: LayoutDashboardIcon },
  { title: "Profile", url: "/app/profile", icon: UserRoundIcon },
  { title: "Settings", url: "/app/settings", icon: SettingsIcon },
]

const ADMINISTRATION: NavItem[] = [
  { title: "Users", url: "/app/admin/users", icon: UsersIcon, nested: true },
]

export function AppSidebar() {
  const { isAdmin } = useAuth()
  const { pathname } = useLocation()

  const isActive = (item: NavItem) =>
    item.nested ? pathname.startsWith(item.url) : pathname === item.url

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
        {renderGroup("Platform", PLATFORM)}
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
