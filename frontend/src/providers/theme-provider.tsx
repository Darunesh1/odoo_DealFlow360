import { ThemeProvider as NextThemesProvider } from "next-themes"
import type { ReactNode } from "react"

import { STORAGE_KEYS } from "@/config"

/**
 * next-themes writes the `dark` class onto <html>, which is what the
 * `@custom-variant dark` rule in index.css keys off. It ships with the shadcn
 * toaster, so the toasts follow the theme with no extra wiring.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey={STORAGE_KEYS.theme}
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  )
}
