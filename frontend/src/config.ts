/**
 * Single place to rebrand the application. Everything user facing reads from here.
 */
export const APP_NAME = "DealFlow360"
export const APP_TAGLINE = "The backbone your product is built on"

/** Base URL of the API. */
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api"

/** Interactive API reference served by the backend. */
export const API_DOCS_URL = API_URL.replace(/\/api\/?$/, "") + "/docs"

export const STORAGE_KEYS = {
  accessToken: "dealflow360.access_token",
  refreshToken: "dealflow360.refresh_token",
  theme: "dealflow360.theme",
} as const
