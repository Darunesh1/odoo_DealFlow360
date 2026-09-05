import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link } from "react-router-dom"
import { MailCheckIcon } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { FormAlert } from "@/components/form-alert"
import { PasswordInput } from "@/components/password-input"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { signupSchema, type SignupValues } from "@/features/auth/schemas"
import { api, errorMessage } from "@/lib/api"
import type { Message } from "@/types/api"

export default function SignupPage() {
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      full_name: "",
      company_name: "",
      email: "",
      password: "",
      confirm_password: "",
    },
  })

  const onSubmit = async (values: SignupValues) => {
    setError(null)
    try {
      await api.post<Message>("/auth/register", {
        full_name: values.full_name,
        email: values.email,
        password: values.password,
        // Sent only when filled in: an individual signs up under their own name.
        company_name: values.company_name?.trim() || null,
      })
      setSent(true)
    } catch (caught) {
      setError(errorMessage(caught, "Could not create your account."))
    }
  }

  // The response is deliberately identical whether or not the address was
  // already taken, so this screen never confirms an address is registered.
  if (sent) {
    return (
      <AuthCard
        title="Check your email"
        description="We have sent you a link to confirm your address."
        footer={
          <>
            Already confirmed?{" "}
            <Link to="/login" className="underline underline-offset-4 hover:text-foreground">
              Sign in
            </Link>
          </>
        }
      >
        <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
          <MailCheckIcon className="mt-0.5 size-4 shrink-0 text-brass" />
          <p className="text-muted-foreground">
            Open the link to activate your account. You will then be able to sign
            in and view the quotations your account manager sends you.
          </p>
        </div>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Create your account"
      description="Sign up to view and negotiate your quotations online."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="underline underline-offset-4 hover:text-foreground">
            Sign in
          </Link>
        </>
      }
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <FormAlert message={error} />

          <FormField
            control={form.control}
            name="full_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Your name</FormLabel>
                <FormControl>
                  <Input autoComplete="name" placeholder="Priya Raman" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="company_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Company</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="organization"
                    placeholder="NovaTech Systems"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Optional. Leave blank if you are buying as an individual.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <PasswordInput autoComplete="new-password" {...field} />
                </FormControl>
                <FormDescription>
                  At least 8 characters, with a letter and a digit.
                </FormDescription>
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

          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Creating your account…" : "Create account"}
          </Button>
        </form>
      </Form>
    </AuthCard>
  )
}
