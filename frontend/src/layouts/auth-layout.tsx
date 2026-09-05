import { Link, Outlet } from "react-router-dom"

import { Brand } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { APP_NAME } from "@/config"

/**
 * A single centred column. The hairline grid behind it is the same ruled
 * language the landing page uses, so signing in feels like the same product.
 */
export function AuthLayout() {
  return (
    <div className="relative flex min-h-svh flex-col bg-muted/30">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 [background-image:linear-gradient(to_right,var(--border)_1px,transparent_1px)] [background-size:5rem_100%] opacity-60"
      />

      <header className="relative flex h-16 items-center justify-between px-4 sm:px-8">
        <Brand />
        <ModeToggle />
      </header>

      <main className="relative flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-[26rem]">
          <Outlet />
        </div>
      </main>

      <footer className="relative px-4 py-6 text-center sm:px-8">
        <p className="text-xs text-muted-foreground">
          <Link to="/" className="underline-offset-4 hover:underline">
            Back to {APP_NAME}
          </Link>
        </p>
      </footer>
    </div>
  )
}
