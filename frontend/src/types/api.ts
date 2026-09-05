/** Mirrors Role in backend/app/models/user.py. A user may hold several. */
export const ROLES = ["admin", "sales_rep", "sales_manager", "finance", "customer"] as const

export type Role = (typeof ROLES)[number]

/** Human labels for each role, used everywhere a role is displayed. */
export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  sales_rep: "Sales Rep",
  sales_manager: "Sales Manager",
  finance: "Finance / Ops",
  customer: "Customer",
}

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  /** False while an invitation has been sent but not yet accepted. */
  is_verified: boolean
  roles: Role[]
  created_at: string
  updated_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Message {
  message: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

/** Shape of FastAPI's error responses: a string, or a list of validation errors. */
export interface ApiErrorBody {
  detail?: string | { msg: string; loc?: (string | number)[] }[]
}
