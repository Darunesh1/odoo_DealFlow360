import { zodResolver } from "@hookform/resolvers/zod"
import { MailCheckIcon } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link } from "react-router-dom"

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
import { registerSchema, type RegisterValues } from "@/features/auth/schemas"
import { useAuth } from "@/features/auth/use-auth"
import { errorMessage } from "@/lib/api"

export default function RegisterPage() {
  const { register } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null)

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: "", email: "", password: "", confirm_password: "" },
  })

  const onSubmit = async (values: RegisterValues) => {
    setError(null)
    try {
      await register(values.full_name, values.email, values.password)
      setRegisteredEmail(values.email)
    } catch (caught) {
      setError(errorMessage(caught, "Could not create your account."))
    }
  }

  if (registeredEmail) {
    return (
      <AuthCard
        title="Check your email"
        description={`A verification link is on its way to ${registeredEmail}.`}
        footer={
          <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
            Continue to sign in
          </Link>
        }
      >
        <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
          <MailCheckIcon className="mt-0.5 size-5 shrink-0 text-primary" />
          <p className="text-sm text-muted-foreground">
            Open the link to activate your account. The link is valid for 24 hours. If it
            does not arrive, check your spam folder or request a new one from the sign-in
            screen.
          </p>
        </div>
      </AuthCard>
    )
  }

  return (
    <AuthCard
      title="Create your account"
      description="Set up an account in under a minute."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
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
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input autoComplete="name" placeholder="Ada Lovelace" {...field} />
                </FormControl>
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
                  At least 8 characters, including a letter and a digit.
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
            {form.formState.isSubmitting ? "Creating account…" : "Create account"}
          </Button>
        </form>
      </Form>
    </AuthCard>
  )
}
