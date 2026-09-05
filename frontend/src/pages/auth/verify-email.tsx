import { useMutation } from "@tanstack/react-query"
import { CircleCheckIcon, Loader2Icon, OctagonXIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"

import { AuthCard } from "@/components/auth-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, errorMessage } from "@/lib/api"
import type { Message } from "@/types/api"

type Status = "verifying" | "verified" | "failed" | "missing"

export default function VerifyEmailPage() {
  // Read the token from the raw query string: it is a JWT, and the router's
  // parser is not needed for a single value.
  const token = new URLSearchParams(window.location.search).get("token")

  const [status, setStatus] = useState<Status>(token ? "verifying" : "missing")
  const [message, setMessage] = useState("")
  const [resendEmail, setResendEmail] = useState("")
  const [resent, setResent] = useState(false)
  // React 19 StrictMode mounts effects twice in development; verifying once is enough.
  const attempted = useRef(false)

  useEffect(() => {
    if (!token || attempted.current) return
    attempted.current = true

    api
      .post<Message>("/auth/verify-email", { token })
      .then(({ data }) => {
        setStatus("verified")
        setMessage(data.message)
      })
      .catch((caught) => {
        setStatus("failed")
        setMessage(errorMessage(caught, "This verification link is not valid."))
      })
  }, [token])

  const resend = useMutation({
    mutationFn: async (email: string) => {
      await api.post("/auth/resend-verification", { email })
    },
    onSuccess: () => setResent(true),
  })

  if (status === "verifying") {
    return (
      <AuthCard title="Verifying your email" description="This only takes a moment.">
        <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-4 text-sm text-muted-foreground">
          <Loader2Icon className="size-5 shrink-0 animate-spin text-primary" />
          Checking your verification link.
        </div>
      </AuthCard>
    )
  }

  if (status === "verified") {
    return (
      <AuthCard title="Email verified" description={message}>
        <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
          <CircleCheckIcon className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className="text-sm text-muted-foreground">
            Your account is active. Sign in to pick up where you left off.
          </p>
        </div>
        <Button asChild className="w-full">
          <Link to="/login">Sign in</Link>
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title={status === "missing" ? "This link is incomplete" : "Verification failed"}
      description={
        status === "missing"
          ? "The verification link is missing its token."
          : message
      }
      footer={
        <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
        <OctagonXIcon className="mt-0.5 size-5 shrink-0 text-destructive" />
        <p className="text-sm text-muted-foreground">
          Verification links expire after 24 hours. Enter your email and we'll send a new one.
        </p>
      </div>

      {resent ? (
        <p className="text-sm text-muted-foreground">
          If an account exists for that address, a new link is on its way.
        </p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            resend.mutate(resendEmail)
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="resend-email">Email</Label>
            <Input
              id="resend-email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={resendEmail}
              onChange={(event) => setResendEmail(event.target.value)}
            />
          </div>
          <Button type="submit" variant="outline" className="w-full" disabled={resend.isPending}>
            {resend.isPending ? "Sending…" : "Send a new link"}
          </Button>
        </form>
      )}
    </AuthCard>
  )
}
