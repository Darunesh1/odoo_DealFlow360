import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "@/features/auth/use-auth"
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
  const { isAuthenticated, isBootstrapping } = useAuth()
  const location = useLocation()

  if (isBootstrapping) return <Resolving />
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return <>{children}</>
}

/** Keeps signed-in people out of the sign-in screens. */
export function RequireGuest({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping } = useAuth()

  if (isBootstrapping) return <Resolving />
  if (isAuthenticated) return <Navigate to="/app" replace />
  return <>{children}</>
}

/** Admin-only routes. Sends non-admins back to the dashboard rather than to login. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, isBootstrapping } = useAuth()

  if (isBootstrapping) return <Resolving />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!user?.is_superuser) return <Navigate to="/app" replace />
  return <>{children}</>
}
