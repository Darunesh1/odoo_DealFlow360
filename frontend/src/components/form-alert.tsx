import { OctagonXIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"

/** Inline form-level error. Field-level messages stay on their own fields. */
export function FormAlert({ message }: { message?: string | null }) {
  if (!message) return null

  return (
    <Alert variant="destructive">
      <OctagonXIcon />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
