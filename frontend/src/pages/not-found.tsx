import { Link } from "react-router-dom"

import { KeelMark } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Button } from "@/components/ui/button"

export default function NotFoundPage() {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center px-4 text-center">
      <div className="absolute top-4 right-4">
        <ModeToggle />
      </div>

      <KeelMark className="size-8 text-primary" />
      <p className="label-mono mt-6 text-muted-foreground">Error 404</p>
      <h1 className="mt-3 text-3xl font-semibold">This page does not exist</h1>
      <p className="mt-3 max-w-sm text-pretty text-muted-foreground">
        The address may be mistyped, or the page may have moved since you last saw it.
      </p>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Button asChild>
          <Link to="/">Go to the home page</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/app">Open the app</Link>
        </Button>
      </div>
    </div>
  )
}
