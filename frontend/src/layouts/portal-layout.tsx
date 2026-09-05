import { Link, NavLink, Outlet } from "react-router-dom"

import { Brand } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/use-auth"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/portal", label: "My Quotations", end: true },
  { to: "/portal/invoices", label: "Invoices", end: false },
  { to: "/portal/profile", label: "Profile", end: false },
]

/**
 * The customer's shell.
 *
 * Deliberately not the internal AppLayout with a different sidebar: the spec
 * asks for "a real, separate, restricted view, not just another internal
 * screen with a different label". No sidebar, no admin surface, no way to
 * navigate anywhere internal.
 */
export function PortalLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <Brand to="/portal" />
          <nav className="hidden items-center gap-1 sm:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    isActive
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground md:inline">
              {user?.full_name ?? user?.email}
            </span>
            <ModeToggle />
            <Button variant="outline" size="sm" onClick={() => logout()}>
              Sign out
            </Button>
          </div>
        </div>
        <nav className="flex gap-1 border-t px-4 py-2 sm:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm",
                  isActive ? "bg-muted font-medium" : "text-muted-foreground"
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t px-4 py-4 text-center text-xs text-muted-foreground">
        Questions about your quotation? Leave a comment on the line and your
        account manager will reply here.{" "}
        <Link to="/portal" className="underline underline-offset-4">
          Back to your quotations
        </Link>
      </footer>
    </div>
  )
}
