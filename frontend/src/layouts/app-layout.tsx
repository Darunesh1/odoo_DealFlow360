import { Outlet, useLocation } from "react-router-dom"

import { AppSidebar } from "@/components/app-sidebar"
import { ModeToggle } from "@/components/mode-toggle"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"

/** Human readable names for the segments that appear after /app. */
const SEGMENT_LABELS: Record<string, string> = {
  app: "Dashboard",
  profile: "Profile",
  settings: "Settings",
  admin: "Administration",
  users: "Users",
}

function useBreadcrumbs() {
  const { pathname } = useLocation()
  const segments = pathname.split("/").filter(Boolean)
  return segments.map((segment) => SEGMENT_LABELS[segment] ?? segment)
}

export function AppLayout() {
  const crumbs = useBreadcrumbs()

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur-sm">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              {crumbs.map((crumb, index) => (
                <BreadcrumbItem key={`${crumb}-${index}`}>
                  {index > 0 && <BreadcrumbSeparator className="mr-1.5" />}
                  <BreadcrumbPage
                    className={
                      index === crumbs.length - 1
                        ? "font-medium text-foreground"
                        : "text-muted-foreground"
                    }
                  >
                    {crumb}
                  </BreadcrumbPage>
                </BreadcrumbItem>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
          <div className="ml-auto">
            <ModeToggle />
          </div>
        </header>

        <div className="flex-1 p-4 md:p-8">
          <div className="mx-auto w-full max-w-5xl space-y-8">
            <Outlet />
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
