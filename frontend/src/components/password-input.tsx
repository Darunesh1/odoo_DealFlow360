import { EyeIcon, EyeOffIcon } from "lucide-react"
import * as React from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export function PasswordInput({
  className,
  ...props
}: React.ComponentProps<typeof Input>) {
  const [revealed, setRevealed] = React.useState(false)

  return (
    <div className="relative">
      <Input
        {...props}
        type={revealed ? "text" : "password"}
        className={cn("pr-10", className)}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        tabIndex={-1}
        onClick={() => setRevealed((value) => !value)}
        aria-label={revealed ? "Hide password" : "Show password"}
        className="absolute top-1/2 right-1 size-7 -translate-y-1/2 text-muted-foreground"
      >
        {revealed ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
      </Button>
    </div>
  )
}
