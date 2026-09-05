import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import { api, setSessionExpiredHandler } from "@/lib/api"
import { tokenStore } from "@/lib/tokens"
import type { TokenPair, User } from "@/types/api"

export interface AuthContextValue {
  user: User | null
  /** True while the stored session is still being resolved on first paint. */
  isBootstrapping: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (fullName: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [hasSession, setHasSession] = useState(() => Boolean(tokenStore.getAccess()))

  const {
    data: user,
    isLoading,
    isFetched,
  } = useQuery({
    queryKey: ["me"],
    queryFn: async () => (await api.get<User>("/users/me")).data,
    enabled: hasSession,
  })

  const endSession = useCallback(() => {
    tokenStore.clear()
    setHasSession(false)
    queryClient.removeQueries({ queryKey: ["me"] })
  }, [queryClient])

  // The interceptor calls this once a refresh has definitively failed.
  useEffect(() => {
    setSessionExpiredHandler(endSession)
  }, [endSession])

  const login = useCallback(
    async (email: string, password: string) => {
      // The token endpoint is OAuth2 password flow, so it takes form encoding.
      const form = new URLSearchParams({ username: email, password })
      const { data } = await api.post<TokenPair>("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      })

      tokenStore.save(data.access_token, data.refresh_token)
      setHasSession(true)
      // Await the profile so callers can navigate into a populated app shell.
      await queryClient.fetchQuery({
        queryKey: ["me"],
        queryFn: async () => (await api.get<User>("/users/me")).data,
      })
    },
    [queryClient]
  )

  const register = useCallback(
    async (fullName: string, email: string, password: string) => {
      await api.post("/auth/register", { email, password, full_name: fullName })
    },
    []
  )

  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefresh()
    if (refreshToken) {
      // Best effort: the local session ends either way.
      await api.post("/auth/logout", { refresh_token: refreshToken }).catch(() => {})
    }
    endSession()
    queryClient.clear()
  }, [endSession, queryClient])

  const refreshUser = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["me"] })
  }, [queryClient])

  const value = useMemo<AuthContextValue>(
    () => ({
      user: user ?? null,
      isBootstrapping: hasSession && isLoading && !isFetched,
      isAuthenticated: hasSession && Boolean(user),
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, hasSession, isLoading, isFetched, login, register, logout, refreshUser]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
