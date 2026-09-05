import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"

import { initialsFor } from "@/components/nav-user"
import { PageHeader } from "@/components/page-header"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
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
import { Input } from "@/components/ui/input"
import { profileSchema, type ProfileValues } from "@/features/auth/schemas"
import { useAuth } from "@/features/auth/use-auth"
import { api, errorMessage } from "@/lib/api"
import type { User } from "@/types/api"

export default function ProfilePage() {
  const { user, refreshUser } = useAuth()

  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: "", email: "" },
  })

  // The profile arrives asynchronously, so seed the form once it lands.
  const { reset } = form
  useEffect(() => {
    if (user) {
      reset({ full_name: user.full_name ?? "", email: user.email })
    }
  }, [user, reset])

  const save = useMutation({
    mutationFn: async (values: ProfileValues) => {
      const { data } = await api.patch<User>("/users/me", values)
      return data
    },
    onSuccess: async (updated) => {
      await refreshUser()
      toast.success(
        updated.is_verified
          ? "Profile updated."
          : "Profile updated. Confirm your new email address to finish."
      )
    },
    onError: (error) => toast.error(errorMessage(error, "Could not save your profile.")),
  })

  if (!user) return null

  const emailChanged = form.watch("email") !== user.email

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Profile"
        description="How you appear across the app, and the address we use to reach you."
      />

      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            <Avatar className="size-12 rounded-lg">
              <AvatarFallback className="rounded-lg bg-primary/10 font-mono text-sm font-medium text-primary">
                {initialsFor(user.full_name, user.email)}
              </AvatarFallback>
            </Avatar>
            <div className="space-y-1">
              <CardTitle className="text-base">
                {user.full_name?.trim() || user.email.split("@")[0]}
              </CardTitle>
              <CardDescription className="flex items-center gap-2">
                {user.email}
                <Badge variant={user.is_verified ? "secondary" : "outline"}>
                  {user.is_verified ? "Verified" : "Unverified"}
                </Badge>
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((values) => save.mutate(values))}
              className="max-w-md space-y-4"
            >
              <FormField
                control={form.control}
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input autoComplete="name" {...field} />
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
                      <Input type="email" autoComplete="email" {...field} />
                    </FormControl>
                    {emailChanged && (
                      <FormDescription>
                        Changing this sends a new confirmation link and marks the account
                        unverified until you open it.
                      </FormDescription>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex items-center gap-3">
                <Button type="submit" disabled={save.isPending || !form.formState.isDirty}>
                  {save.isPending ? "Saving…" : "Save changes"}
                </Button>
                {form.formState.isDirty && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      reset({ full_name: user.full_name ?? "", email: user.email })
                    }
                  >
                    Discard
                  </Button>
                )}
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </>
  )
}
