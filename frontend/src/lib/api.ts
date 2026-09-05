import axios, { AxiosError, type AxiosRequestConfig } from "axios"

import { API_URL } from "@/config"
import { tokenStore } from "@/lib/tokens"
import type { ApiErrorBody, TokenPair } from "@/types/api"

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
})

/** Bare client for the refresh call, so a failing refresh cannot recurse. */
const refreshClient = axios.create({ baseURL: API_URL })

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * Single-flight refresh.
 *
 * When several requests fail with 401 at once, only the first one calls
 * /auth/refresh; the rest wait on the same promise and are replayed with the
 * new token. Without this, a page that loads four resources would burn four
 * refresh tokens and three of them would already be revoked by rotation.
 */
let refreshInFlight: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStore.getRefresh()
  if (!refreshToken) {
    throw new Error("No refresh token available")
  }

  const { data } = await refreshClient.post<TokenPair>("/auth/refresh", {
    refresh_token: refreshToken,
  })
  tokenStore.save(data.access_token, data.refresh_token)
  return data.access_token
}

/** Called when a session can no longer be recovered. Set by the auth provider. */
let onSessionExpired: () => void = () => {}

export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined

    const isAuthEndpoint = original?.url?.startsWith("/auth/")
    if (
      error.response?.status !== 401 ||
      !original ||
      original._retried ||
      isAuthEndpoint ||
      !tokenStore.getRefresh()
    ) {
      return Promise.reject(error)
    }

    original._retried = true

    try {
      refreshInFlight ??= refreshAccessToken().finally(() => {
        refreshInFlight = null
      })
      const token = await refreshInFlight
      original.headers = { ...original.headers, Authorization: `Bearer ${token}` }
      return api(original)
    } catch {
      tokenStore.clear()
      onSessionExpired()
      return Promise.reject(error)
    }
  }
)

/**
 * Turns any thrown value into a sentence worth showing a person.
 * FastAPI returns `detail` as a string, or as a list of validation errors.
 */
export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((item) => item.msg).join(", ")
    }
    if (error.code === "ERR_NETWORK") {
      return "Cannot reach the API. Is the backend running?"
    }
  }
  return fallback
}
