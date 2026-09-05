import { useMutation } from "@tanstack/react-query"
import {
  ArrowRightIcon,
  BookOpenIcon,
  CircleCheckIcon,
  MailWarningIcon,
  ShieldCheckIcon,
  UserRoundIcon,
} from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { API_DOCS_URL, APP_NAME } from "@/config"
import { useAuth } from "@/features/auth/use-auth"
import { ROLE_LABELS } from "@/types/api"
import { api, errorMessage } from "@/lib/api"

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "long",
  year: "numeric",
})

/** Facts drawn from the signed-in account, not placeholder metrics. */
function AccountFacts() {
  const { user } = useAuth()
  if (!user) return null

  const facts = [
    { label: "Member since", value: dateFormatter.format(new Date(user.created_at)) },
    {
      label: user.roles.length === 1 ? "Role" : "Roles",
      value: user.roles.map((role) => ROLE_LABELS[role]).join(", ") || "None assigned",
    },
    { label: "Email status", value: user.is_verified ? "Verified" : "Unverified" },
    { label: "Account ID", value: user.id.slice(0, 8), mono: true },
  ]

  return (
    <div className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-4">
      {facts.map((fact) => (
        <div key={fact.label} className="bg-card p-4">
          <p className="label-mono text-muted-foreground">{fact.label}</p>
          <p
            className={
              fact.mono
                ? "mt-1.5 font-mono text-sm font-medium"
                : "mt-1.5 text-sm font-medium"
            }
          >
            {fact.value}
          </p>
        </div>
      ))}
    </div>
  )
}

function VerificationNotice() {
  const { user } = useAuth()

  const resend = useMutation({
    mutationFn: async () => {
      await api.post("/auth/resend-verification", { email: user?.email })
    },
    onSuccess: () => toast.success("Verification email sent. Check your inbox."),
    onError: (error) => toast.error(errorMessage(error, "Could not send the email.")),
  })

  if (!user || user.is_verified) return null

  return (
    <Card className="border-brass/40 bg-brass/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MailWarningIcon className="size-4 text-brass" />
          Confirm your email address
        </CardTitle>
        <CardDescription>
          We sent a link to {user.email}. Confirming it keeps your account recoverable if
          you forget your password.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="outline" onClick={() => resend.mutate()} disabled={resend.isPending}>
          {resend.isPending ? "Sending…" : "Send the link again"}
        </Button>
      </CardContent>
    </Card>
  )
}

const NEXT_STEPS = [
  {
    title: "Complete your profile",
    description: "Set the name that appears across the app.",
    to: "/app/profile",
    icon: UserRoundIcon,
  },
  {
    title: "Secure your account",
    description: "Change your password and pick a theme.",
    to: "/app/settings",
    icon: ShieldCheckIcon,
  },
]

export default function DashboardPage() {
  const { user, isAdmin } = useAuth()
  const firstName = user?.full_name?.trim().split(" ")[0]

  return (
    <>
      <PageHeader
        eyebrow="Dashboard"
        title={firstName ? `Welcome back, ${firstName}` : "Welcome back"}
        description={`Your ${APP_NAME} account at a glance. Replace this screen with whatever your product does.`}
      />

      <VerificationNotice />
      <AccountFacts />

      <div className="grid gap-4 md:grid-cols-2">
        {NEXT_STEPS.map((step) => (
          <Card key={step.to} className="transition-colors hover:border-primary/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <step.icon className="size-4 text-primary" />
                {step.title}
              </CardTitle>
              <CardDescription>{step.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="ghost" size="sm" className="-ml-2">
                <Link to={step.to}>
                  Open
                  <ArrowRightIcon className="size-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BookOpenIcon className="size-4 text-primary" />
            Build the next screen
          </CardTitle>
          <CardDescription>
            Every route this app calls is documented and testable in the interactive API
            reference.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <a href={API_DOCS_URL} target="_blank" rel="noreferrer">
              Open API reference
            </a>
          </Button>
          {isAdmin && (
            <Badge variant="secondary" className="gap-1.5">
              <CircleCheckIcon className="size-3" />
              Admin tools unlocked
            </Badge>
          )}
        </CardContent>
      </Card>
    </>
  )
}
