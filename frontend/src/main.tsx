import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import App from "@/App"
import { TooltipProvider } from "@/components/ui/tooltip"
import { QueryProvider } from "@/providers/query-provider"
import { ThemeProvider } from "@/providers/theme-provider"
import "@/index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryProvider>
        {/* Radix tooltips need a provider above them; the collapsed sidebar uses one per item. */}
        <TooltipProvider>
          <App />
        </TooltipProvider>
      </QueryProvider>
    </ThemeProvider>
  </StrictMode>
)
