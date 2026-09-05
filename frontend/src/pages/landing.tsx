import {
  ArrowRightIcon,
  CheckIcon,
  DatabaseIcon,
  KeyRoundIcon,
  ListChecksIcon,
  MailIcon,
  PaletteIcon,
  UsersIcon,
} from "lucide-react"
import { Link } from "react-router-dom"

import { KeelMark } from "@/components/brand"
import { SectionRail, type RailSection } from "@/components/section-rail"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { API_DOCS_URL, APP_NAME } from "@/config"
import { useAuth } from "@/features/auth/use-auth"
import { cn } from "@/lib/utils"

const SECTIONS: RailSection[] = [
  { id: "top", label: "Start" },
  { id: "features", label: "Included" },
  { id: "stack", label: "Stack" },
  { id: "pricing", label: "Plans" },
  { id: "faq", label: "Questions" },
]

/** The routes the API actually serves. Doubles as the hero's proof. */
const ROUTES = [
  { method: "POST", path: "/auth/register" },
  { method: "POST", path: "/auth/login" },
  { method: "POST", path: "/auth/refresh" },
  { method: "POST", path: "/auth/logout" },
  { method: "POST", path: "/auth/verify-email" },
  { method: "POST", path: "/auth/forgot-password" },
  { method: "POST", path: "/auth/reset-password" },
  { method: "GET", path: "/users/me" },
  { method: "PATCH", path: "/users/me" },
  { method: "GET", path: "/admin/users" },
] as const

const METHOD_STYLES: Record<string, string> = {
  GET: "text-primary",
  POST: "text-brass",
  PATCH: "text-muted-foreground",
}

const FEATURES = [
  {
    icon: KeyRoundIcon,
    title: "Authentication that holds up",
    body: "Access and refresh tokens with rotation, a Redis deny list for revoked sessions, and single-flight refresh on the client.",
  },
  {
    icon: MailIcon,
    title: "Email flows, done",
    body: "Verification, resend, forgotten password, and reset. Without SMTP configured, mail is printed to the worker log instead.",
  },
  {
    icon: UsersIcon,
    title: "Roles and an admin area",
    body: "A paginated, searchable user list with activate, promote, and delete. Self-service routes cannot touch privilege fields.",
  },
  {
    icon: ListChecksIcon,
    title: "Forms with one source of truth",
    body: "Zod schemas mirror the API's own validation rules, so the client and the server agree on what a valid password is.",
  },
  {
    icon: PaletteIcon,
    title: "Light and dark, everywhere",
    body: "One token set drives both themes across every screen. Change two variables to rebrand the whole application.",
  },
  {
    icon: DatabaseIcon,
    title: "Ready to operate",
    body: "Liveness and readiness probes that check Postgres and Redis, plus a background worker for anything slow.",
  },
]

const STATS = [
  { value: "18", label: "API routes" },
  { value: "41", label: "Tests passing" },
  { value: "2", label: "Containers to run" },
  { value: "0", label: "Config to write" },
]

const PLANS = [
  {
    name: "Starter",
    price: "$0",
    cadence: "forever",
    description: "For side projects and prototypes.",
    features: ["Up to 3 team members", "Community support", "1 GB storage"],
    cta: "Get started",
    featured: false,
  },
  {
    name: "Team",
    price: "$29",
    cadence: "per user / month",
    description: "For teams shipping to real customers.",
    features: [
      "Unlimited team members",
      "Priority support",
      "100 GB storage",
      "Audit log and SSO",
    ],
    cta: "Start free trial",
    featured: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    cadence: "annual",
    description: "For organisations with procurement.",
    features: ["Dedicated infrastructure", "99.9% uptime SLA", "Security review"],
    cta: "Contact sales",
    featured: false,
  },
]

const FAQS = [
  {
    question: `What do I get when I clone ${APP_NAME}?`,
    answer:
      "A FastAPI backend with async SQLAlchemy, PostgreSQL, Redis and Celery, and this React frontend built on shadcn/ui. Registration, email verification, password reset, sessions, an admin area and health probes are already wired end to end.",
  },
  {
    question: "How do I run it locally?",
    answer:
      "Docker runs Postgres and Redis; everything else runs natively so it reloads instantly. Run `make install`, then `make api`, `make worker` and `make web` in three terminals. `make help` lists the rest.",
  },
  {
    question: "Do I need to configure SMTP to try it?",
    answer:
      "No. With no SMTP credentials set, every email is printed to the Celery worker log instead of being sent, so you can copy a verification link straight out of your terminal.",
  },
  {
    question: "How do I make this look like my product?",
    answer:
      "Change APP_NAME in src/config.ts, then edit the --primary and --brass variables in src/index.css. Both themes and every component follow from those tokens.",
  },
  {
    question: "Is the pricing section real?",
    answer:
      "No, it is placeholder scaffolding. It is here so you have a well-built section to point at your own plans rather than building one from scratch.",
  },
]

function Section({
  id,
  className,
  children,
}: {
  id: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className={cn("scroll-mt-20 border-b", className)}>
      <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 md:py-28">{children}</div>
    </section>
  )
}

function SectionIntro({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <div className="max-w-2xl">
      <p className="label-mono text-primary">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold text-balance md:text-4xl">{title}</h2>
      <p className="mt-4 text-base text-pretty text-muted-foreground">{description}</p>
    </div>
  )
}

function Hero() {
  const { isAuthenticated } = useAuth()

  return (
    <section id="top" className="relative scroll-mt-20 overflow-hidden border-b">
      {/* Station lines: the same ruled language the section rail uses. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 [background-image:linear-gradient(to_right,var(--border)_1px,transparent_1px)] [background-size:6rem_100%] opacity-70"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-background to-transparent"
      />

      <div className="relative mx-auto grid w-full max-w-6xl gap-14 px-4 py-20 sm:px-6 md:py-28 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <div>
          <p className="label-mono animate-rise text-muted-foreground" style={{ "--rise-delay": "0ms" } as React.CSSProperties}>
            FastAPI · React · PostgreSQL
          </p>

          <h1
            className="animate-rise mt-5 text-4xl font-semibold text-balance sm:text-5xl md:text-6xl"
            style={{ "--rise-delay": "60ms" } as React.CSSProperties}
          >
            Lay the keel,
            <br />
            then build the ship.
          </h1>

          <p
            className="animate-rise mt-6 max-w-lg text-lg text-pretty text-muted-foreground"
            style={{ "--rise-delay": "120ms" } as React.CSSProperties}
          >
            Accounts, sessions, email flows and an admin area, already working together.
            Start on the part of your product that is actually yours.
          </p>

          <div
            className="animate-rise mt-8 flex flex-wrap items-center gap-3"
            style={{ "--rise-delay": "180ms" } as React.CSSProperties}
          >
            <Button asChild size="lg">
              <Link to={isAuthenticated ? "/app" : "/register"}>
                {isAuthenticated ? "Open the app" : "Get started"}
                <ArrowRightIcon className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <a href={API_DOCS_URL} target="_blank" rel="noreferrer">
                View the API
              </a>
            </Button>
          </div>

          <p
            className="animate-rise mt-8 font-mono text-xs text-muted-foreground"
            style={{ "--rise-delay": "240ms" } as React.CSSProperties}
          >
            <span className="text-primary">$</span> make install &amp;&amp; make api
          </p>
        </div>

        {/* The proof: the routes you get before writing a line of your own. */}
        <div
          className="animate-rise"
          style={{ "--rise-delay": "300ms" } as React.CSSProperties}
        >
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <KeelMark className="size-4 text-primary" />
              <span className="label-mono text-muted-foreground">Working on day zero</span>
              <span className="ml-auto font-mono text-xs text-muted-foreground">
                /api/v1
              </span>
            </div>
            <ul className="divide-y">
              {ROUTES.map((route) => (
                <li
                  key={`${route.method} ${route.path}`}
                  className="flex items-center gap-4 px-4 py-2.5"
                >
                  <span
                    className={cn(
                      "w-12 shrink-0 font-mono text-[0.6875rem] font-semibold",
                      METHOD_STYLES[route.method]
                    )}
                  >
                    {route.method}
                  </span>
                  <span className="truncate font-mono text-sm">{route.path}</span>
                  <CheckIcon className="ml-auto size-3.5 shrink-0 text-muted-foreground/50" />
                </li>
              ))}
            </ul>
            <div className="border-t bg-muted/40 px-4 py-2.5">
              <span className="label-mono text-muted-foreground">
                and 8 more, all documented
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function LandingPage() {
  const { isAuthenticated } = useAuth()

  return (
    <>
      <SectionRail sections={SECTIONS} />
      <Hero />

      <Section id="features">
        <SectionIntro
          eyebrow="Included"
          title="The parts every product needs, already assembled"
          description="Not a scaffold that stubs things out. These flows run against a real database, a real cache and a real background worker."
        />

        <div className="mt-14 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="bg-card p-6 transition-colors hover:bg-muted/40">
              <feature.icon className="size-5 text-primary" />
              <h3 className="mt-4 text-base font-semibold">{feature.title}</h3>
              <p className="mt-2 text-sm text-pretty text-muted-foreground">{feature.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="stack" className="bg-muted/30">
        <div className="grid gap-14 lg:grid-cols-[1fr_1fr] lg:items-center">
          <SectionIntro
            eyebrow="Stack"
            title="Boring where it counts, current where it helps"
            description="PostgreSQL and Redis in containers. FastAPI, a Celery worker and Vite on your machine, reloading the moment you save. One command starts each."
          />

          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border">
            {STATS.map((stat) => (
              <div key={stat.label} className="bg-card p-6">
                <dt className="label-mono text-muted-foreground">{stat.label}</dt>
                <dd className="mt-2 font-heading text-3xl font-semibold tabular-nums">
                  {stat.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </Section>

      <Section id="pricing">
        <SectionIntro
          eyebrow="Plans"
          title="Pricing, ready for your numbers"
          description="Placeholder tiers in a section that already works. Swap the copy and point the buttons at your checkout."
        />

        <div className="mt-14 grid gap-6 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={cn(
                "flex flex-col rounded-xl border bg-card p-6",
                plan.featured && "border-brass/50 ring-1 ring-brass/20"
              )}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-lg font-semibold">{plan.name}</h3>
                {plan.featured && (
                  <Badge variant="outline" className="border-brass/40 text-brass">
                    Recommended
                  </Badge>
                )}
              </div>

              <p className="mt-2 text-sm text-muted-foreground">{plan.description}</p>

              <p className="mt-6 flex items-baseline gap-2">
                <span className="font-heading text-4xl font-semibold tabular-nums">
                  {plan.price}
                </span>
                <span className="text-sm text-muted-foreground">{plan.cadence}</span>
              </p>

              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2.5 text-sm">
                    <CheckIcon
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        plan.featured ? "text-brass" : "text-primary"
                      )}
                    />
                    <span className="text-muted-foreground">{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                asChild
                className="mt-8"
                variant={plan.featured ? "default" : "outline"}
              >
                <Link to={isAuthenticated ? "/app" : "/register"}>{plan.cta}</Link>
              </Button>
            </div>
          ))}
        </div>
      </Section>

      <Section id="faq" className="bg-muted/30">
        <div className="grid gap-14 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionIntro
            eyebrow="Questions"
            title="Before you clone it"
            description="What you get, how to run it, and what to change first."
          />

          <Accordion type="single" collapsible className="w-full">
            {FAQS.map((faq) => (
              <AccordionItem key={faq.question} value={faq.question}>
                <AccordionTrigger className="text-left text-base font-medium">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-sm text-pretty text-muted-foreground">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </Section>

      <section className="border-b">
        <div className="mx-auto w-full max-w-6xl px-4 py-20 text-center sm:px-6 md:py-24">
          <KeelMark className="mx-auto size-8 text-primary" />
          <h2 className="mt-6 text-3xl font-semibold text-balance md:text-4xl">
            Start with the boring parts finished
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-pretty text-muted-foreground">
            Create an account and see the whole flow, from verification email to admin
            table, running on your own machine.
          </p>
          <Button asChild size="lg" className="mt-8">
            <Link to={isAuthenticated ? "/app" : "/register"}>
              {isAuthenticated ? "Open the app" : "Create your account"}
              <ArrowRightIcon className="size-4" />
            </Link>
          </Button>
        </div>
      </section>
    </>
  )
}
