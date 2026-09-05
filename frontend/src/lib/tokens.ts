import { STORAGE_KEYS } from "@/config"

/**
 * Token storage lives behind these helpers so swapping localStorage for cookies
 * later is a one file change.
 */
export const tokenStore = {
  getAccess: () => localStorage.getItem(STORAGE_KEYS.accessToken),
  getRefresh: () => localStorage.getItem(STORAGE_KEYS.refreshToken),

  save(accessToken: string, refreshToken?: string) {
    localStorage.setItem(STORAGE_KEYS.accessToken, accessToken)
    if (refreshToken) {
      localStorage.setItem(STORAGE_KEYS.refreshToken, refreshToken)
    }
  },

  clear() {
    localStorage.removeItem(STORAGE_KEYS.accessToken)
    localStorage.removeItem(STORAGE_KEYS.refreshToken)
  },
}
