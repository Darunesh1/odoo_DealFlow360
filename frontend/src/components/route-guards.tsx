import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "@/features/auth/use-auth"
import type { Role } from "@/types/api"
import { DealFlowMark } from "@/components/brand"

function Resolving() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <DealFlowMark className="size-7 animate-pulse text-muted-foreground" />
      <span className="sr-only">Loading your session</span>
    </div>
  )
}

/** Blocks a route until a session is proven. Remembers where the visitor was headed. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping, isCustomerOnly } = useAuth()
  const location = useLocation()

  if (isBootstrapping) return <Resolving />
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  // A customer has no internal screens at all, so /app is never the right
  // place for them even though they are perfectly well signed in.
  if (isCustomerOnly) return <Navigate to="/portal" replace />
  return <>{children}</>
}

/** Keeps signed-in people out of the sign-in screens. */
export function RequireGuest({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping, landingPath } = useAuth()

  if (isBootstrapping) return <Resolving />
  if (isAuthenticated) return <Navigate to={landingPath} replace />
  return <>{children}</>
}

/**
 * Restricts a route to holders of at least one of `roles`. Roles are additive,
 * so someone who is both a Sales Manager and Finance satisfies either guard.
 * Sends the unauthorized back to the dashboard rather than to login.
 */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { isAuthenticated, isBootstrapping, hasRole, landingPath } = useAuth()

  if (isBootstrapping) return <Resolving />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  // Bounced to wherever this user actually belongs. Sending a customer to
  // /app would land them on an internal shell that every other guard then
  // refuses, which reads as a broken app rather than a closed door.
  if (!hasRole(...roles)) return <Navigate to={landingPath} replace />
  return <>{children}</>
}

/** Admin-only routes. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  return <RequireRole roles={["admin"]}>{children}</RequireRole>
}
