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

  return { ...context, hasRole, isAdmin: hasRole("admin") }
}
