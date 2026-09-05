import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { CircleCheckIcon } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link, useNavigate } from "react-router-dom"

import { AuthCard } from "@/components/auth-card"
import { FormAlert } from "@/components/form-alert"
import { PasswordInput } from "@/components/password-input"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { acceptInviteSchema, type AcceptInviteValues } from "@/features/auth/schemas"
import { api, errorMessage } from "@/lib/api"
import type { Message } from "@/types/api"

/**
 * Where an invited user lands from their email. There is no public signup, so
 * this is how everyone except the seeded administrator gets their password.
 */
export default function AcceptInvitePage() {
  // The token is a JWT, so read it off the raw query string rather than
  // routing it through the router's parser.
  const token = new URLSearchParams(window.location.search).get("token")
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const form = useForm<AcceptInviteValues>({
    resolver: zodResolver(acceptInviteSchema),
    defaultValues: { new_password: "", confirm_password: "" },
  })

  const accept = useMutation({
    mutationFn: async (values: AcceptInviteValues) => {
      const { data } = await api.post<Message>("/auth/accept-invite", {
        token,
        new_password: values.new_password,
      })
      return data
    },
    onSuccess: () => {
      setDone(true)
      setTimeout(() => navigate("/login", { replace: true }), 1500)
    },
    onError: (caught) =>
      setError(errorMessage(caught, "This invitation link is not valid.")),
  })

  if (!token) {
    return (
      <AuthCard
        title="Invitation link incomplete"
        description="This link is missing its token."
      >
        <FormAlert message="Open the link exactly as it appears in your invitation email." />
        <Button asChild variant="outline" className="w-full">
          <Link to="/login">Back to sign in</Link>
        </Button>
      </AuthCard>
    )
  }

  if (done) {
    return (
      <AuthCard title="You're all set" description="Taking you to sign in.">
        <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
          <CircleCheckIcon className="size-5 shrink-0 text-primary" />
          Your password is set. You can sign in now.
        </div>
        <Button asChild className="w-full">
          <Link to="/login">Go to sign in</Link>
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Set your password"
      description="An administrator created an account for you. Choose a password to activate it."
    >
      {error && <FormAlert message={error} />}

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit((values) => {
            setError(null)
            accept.mutate(values)
          })}
          className="space-y-4"
        >
          <FormField
            control={form.control}
            name="new_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>New password</FormLabel>
                <FormControl>
                  <PasswordInput autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="confirm_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Confirm password</FormLabel>
                <FormControl>
                  <PasswordInput autoComplete="new-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" className="w-full" disabled={accept.isPending}>
            {accept.isPending ? "Setting your password…" : "Activate account"}
          </Button>
        </form>
      </Form>
    </AuthCard>
  )
}
