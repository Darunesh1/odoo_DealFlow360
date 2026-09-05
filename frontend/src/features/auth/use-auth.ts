import { useContext } from "react"

import { AuthContext } from "@/features/auth/auth-context"
import type { Role } from "@/types/api"

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider")
  }

  /** True when the signed-in user holds at least one of the given roles. */
  const hasRole = (...roles: Role[]) =>
    roles.some((role) => context.user?.roles.includes(role) ?? false)

  /**
   * Where this user belongs after signing in.
   *
   * A customer's whole world is the portal - they have no internal screens at
   * all - so sending them to /app would land them on a dashboard every guard
   * then refuses.
   */
  const isCustomerOnly =
    Boolean(context.user) &&
    context.user!.roles.length > 0 &&
    context.user!.roles.every((role) => role === "customer")

  return {
    ...context,
    hasRole,
    isAdmin: hasRole("admin"),
    isCustomerOnly,
    landingPath: isCustomerOnly ? "/portal" : "/app",
  }
}
