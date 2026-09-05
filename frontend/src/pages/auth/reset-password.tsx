import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { toast } from "sonner"

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
import {
  resetPasswordSchema,
  type ResetPasswordValues,
} from "@/features/auth/schemas"
import { api, errorMessage } from "@/lib/api"

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token")
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { new_password: "", confirm_password: "" },
  })

  if (!token) {
    return (
      <AuthCard
        title="This link is incomplete"
        description="The reset link is missing its token. Request a new one to continue."
        footer={
          <Link to="/forgot-password" className="font-medium text-foreground underline-offset-4 hover:underline">
            Request a new link
          </Link>
        }
      >
        <FormAlert message="No reset token was found in the address." />
      </AuthCard>
    )
  }

  const onSubmit = async (values: ResetPasswordValues) => {
    setError(null)
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: values.new_password,
      })
      toast.success("Password updated. You can sign in now.")
      navigate("/login", { replace: true })
    } catch (caught) {
      setError(errorMessage(caught, "Could not reset your password."))
    }
  }

  return (
    <AuthCard
      title="Choose a new password"
      description="Pick something you have not used here before."
      footer={
        <Link to="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <FormAlert message={error} />

          <FormField
            control={form.control}
            name="new_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>New password</FormLabel>
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
            {form.formState.isSubmitting ? "Updating…" : "Update password"}
          </Button>
        </form>
      </Form>
    </AuthCard>
  )
}
