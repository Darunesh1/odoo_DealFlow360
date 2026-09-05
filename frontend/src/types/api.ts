export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
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
