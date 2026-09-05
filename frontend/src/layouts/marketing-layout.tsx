import { MenuIcon } from "lucide-react"
import { useState } from "react"
import { Link, Outlet } from "react-router-dom"

import { Brand, DealFlowMark } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { APP_NAME, APP_TAGLINE } from "@/config"
import { useAuth } from "@/features/auth/use-auth"

const NAV = [
  { label: "Modules", href: "/#modules" },
  { label: "Governance", href: "/#governance" },
  { label: "Roles", href: "/#roles" },
  { label: "FAQ", href: "/#faq" },
]

const FOOTER_COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "Modules", href: "/#modules" },
      { label: "Governance", href: "/#governance" },
      { label: "Roles", href: "/#roles" },
      { label: "FAQ", href: "/#faq" },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Sign in", href: "/login" },
      // Public sign-up is for customers; staff accounts are created by an admin.
      { label: "Create a customer account", href: "/signup" },
      { label: "Reset password", href: "/forgot-password" },
    ],
  },
]

function AuthActions({ onNavigate }: { onNavigate?: () => void }) {
  const { isAuthenticated, landingPath } = useAuth()

  if (isAuthenticated) {
    return (
      <Button asChild size="sm" onClick={onNavigate}>
        {/* A customer belongs in the portal, everyone else in the workspace. */}
        <Link to={landingPath}>Open the workspace</Link>
      </Button>
    )
  }

  return (
    <>
      <Button asChild variant="ghost" size="sm" onClick={onNavigate}>
        <Link to="/login">Sign in</Link>
      </Button>
      <Button asChild size="sm" onClick={onNavigate}>
        <Link to="/signup">Create an account</Link>
      </Button>
    </>
  )
}

export function MarketingLayout() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="flex min-h-svh flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Brand />

          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <ModeToggle />
            <div className="hidden items-center gap-1 md:flex">
              <AuthActions />
            </div>

            <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                  <MenuIcon className="size-4" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-72">
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2">
                    <DealFlowMark className="size-4 text-primary" />
                    {APP_NAME}
                  </SheetTitle>
                </SheetHeader>
                <nav className="flex flex-col gap-1 px-4">
                  {NAV.map((item) => (
                    <a
                      key={item.href}
                      href={item.href}
                      onClick={() => setMenuOpen(false)}
                      className="rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {item.label}
                    </a>
                  ))}
                </nav>
                <div className="mt-auto flex flex-col gap-2 p-4">
                  <AuthActions onNavigate={() => setMenuOpen(false)} />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t">
        <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.5fr_1fr_1fr]">
          <div className="space-y-3">
            <Brand />
            <p className="text-sm font-medium">{APP_TAGLINE}</p>
            <p className="max-w-xs text-sm text-muted-foreground">
              Discount approvals that route themselves, multi-warehouse fulfillment,
              hybrid billing, and a portal customers can negotiate in.
            </p>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <div key={column.title}>
              <p className="label-mono text-muted-foreground">{column.title}</p>
              <ul className="mt-4 space-y-2.5">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      to={link.href}
                      className="text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-t">
          <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 sm:px-6">
            <p className="label-mono text-muted-foreground">
              © {new Date().getFullYear()} {APP_NAME}
            </p>
            <p className="label-mono text-muted-foreground">
              Quotation · Approval · Fulfillment · Billing
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
