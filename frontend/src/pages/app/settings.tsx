import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { MonitorIcon, MoonIcon, SunIcon, TriangleAlertIcon } from "lucide-react"
import { useTheme } from "next-themes"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { PasswordInput } from "@/components/password-input"
import { useAuth } from "@/features/auth/use-auth"
import {
  changePasswordSchema,
  type ChangePasswordValues,
} from "@/features/auth/schemas"
import { api, errorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"

const THEMES = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: MonitorIcon },
] as const

function Appearance() {
  const { theme, setTheme } = useTheme()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Appearance</CardTitle>
        <CardDescription>
          Choose a theme, or follow whatever your operating system is set to.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid max-w-md grid-cols-3 gap-3">
          {THEMES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setTheme(option.value)}
              aria-pressed={theme === option.value}
              className={cn(
                "flex flex-col items-center gap-2 rounded-lg border p-4 text-sm transition-colors outline-none",
                "hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50",
                theme === option.value && "border-primary bg-primary/5 text-primary"
              )}
            >
              <option.icon className="size-5" />
              {option.label}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ChangePassword() {
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  })

  const change = useMutation({
    mutationFn: async (values: ChangePasswordValues) => {
      await api.post("/auth/change-password", {
        current_password: values.current_password,
        new_password: values.new_password,
      })
    },
    onSuccess: () => {
      form.reset()
      toast.success("Password changed.")
    },
    onError: (error) =>
      toast.error(errorMessage(error, "Could not change your password.")),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Password</CardTitle>
        <CardDescription>
          You stay signed in on this device after changing it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => change.mutate(values))}
            className="max-w-md space-y-4"
          >
            <FormField
              control={form.control}
              name="current_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Current password</FormLabel>
                  <FormControl>
                    <PasswordInput autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

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
                  <FormLabel>Confirm new password</FormLabel>
                  <FormControl>
                    <PasswordInput autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? "Updating…" : "Change password"}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}

function DangerZone() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const remove = useMutation({
    mutationFn: async () => {
      await api.delete("/users/me")
    },
    onSuccess: async () => {
      await logout()
      toast.success("Your account has been deleted.")
      navigate("/", { replace: true })
    },
    onError: (error) =>
      toast.error(errorMessage(error, "Could not delete your account.")),
  })

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base text-destructive">
          <TriangleAlertIcon className="size-4" />
          Delete account
        </CardTitle>
        <CardDescription>
          Deleting removes your account and everything attached to it. This cannot be undone.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {user?.is_superuser ? (
          <p className="text-sm text-muted-foreground">
            Administrator accounts cannot be deleted from here. Ask another administrator
            to remove it from the user list.
          </p>
        ) : (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">Delete account</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete your account?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently removes {user?.email} and signs you out. There is no way
                  to restore it.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep my account</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => remove.mutate()}
                  disabled={remove.isPending}
                >
                  {remove.isPending ? "Deleting…" : "Delete account"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </CardContent>
    </Card>
  )
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Appearance, credentials, and account removal."
      />
      <Appearance />
      <ChangePassword />
      <DangerZone />
    </>
  )
}
