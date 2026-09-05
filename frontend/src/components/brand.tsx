import { Link } from "react-router-dom"

import { APP_NAME } from "@/config"
import { cn } from "@/lib/utils"

export function DealFlowMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("size-5", className)}
    >
      <path d="M4 4.5 L12 20 L20 4.5" />
      <path d="M12 8.5 L12 20" strokeWidth={1.25} className="opacity-55" />
    </svg>
  )
}

export function Brand({
  className,
  to = "/",
  showName = true,
}: {
  className?: string
  to?: string
  showName?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        "flex items-center gap-2 rounded-md font-heading text-[0.9375rem] font-semibold tracking-[-0.01em] outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className
      )}
    >
      <img 
        src="/logo.png" 
        alt={`${APP_NAME} logo`} 
        className="size-7 rounded-md object-contain" 
      />
      {showName && <span>{APP_NAME}</span>}
    </Link>
  )
}