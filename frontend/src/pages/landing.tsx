import {
  ArrowRightIcon,
  BellIcon,
  CheckIcon,
  GavelIcon,
  MessageSquareIcon,
  RepeatIcon,
  SparklesIcon,
  TruckIcon,
} from "lucide-react"
import { Link } from "react-router-dom"

import { DealFlowMark } from "@/components/brand"
import { SectionRail, type RailSection } from "@/components/section-rail"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { APP_NAME } from "@/config"
import { useAuth } from "@/features/auth/use-auth"
import { cn } from "@/lib/utils"

const SECTIONS: RailSection[] = [
  { id: "top", label: "Start" },
  { id: "modules", label: "Modules" },
  { id: "governance", label: "Governance" },
  { id: "roles", label: "Roles" },
  { id: "faq", label: "Questions" },
]

/**
 * The hero's proof: the worked example from the spec, rendered exactly as the
 * quotation builder renders it. One line inside its limit, one over, and the
 * routing that falls out — the whole product argument in eight rows.
 */
const EXAMPLE_LINES = [
  { product: "Laptop Pro 14", category: "Hardware", given: "12%", allowed: "15%", over: 0 },
  { product: "Onsite Setup", category: "Services", given: "18%", allowed: "10%", over: 8 },
  { product: "Extended Warranty", category: "Services", given: "10%", allowed: "10%", over: 0 },
] as const

const MODULES = [
  {
    icon: GavelIcon,
    title: "Discount governance that routes itself",
    body: "Every line is measured against the stricter of its customer tier and its category ceiling. The blended score decides whether a deal needs a manager, a manager and finance, or nobody at all — the rep never requests approval by hand.",
  },
  {
    icon: SparklesIcon,
    title: "Upsell suggestions with the margin attached",
    body: "Ranked from what sells alongside what is already in the cart, lifted by whatever is promoted this quarter, and suppressed entirely below a minimum margin. Adding one moves the total and the margin indicator immediately.",
  },
  {
    icon: TruckIcon,
    title: "Warehouse splitting and real backorders",
    body: "The planner draws from the fewest warehouses it can, breaks ties on the shipping rates you set, and backorders what nothing covers. When stock lands, it folds into the shipment already planned rather than opening a second one.",
  },
  {
    icon: RepeatIcon,
    title: "Hardware and subscriptions on one order",
    body: "One-time lines bill on despatch; recurring lines bill on their own cycle. Change a quantity mid-period and the unused remainder is prorated, with the arithmetic shown rather than an unexplained adjustment.",
  },
  {
    icon: MessageSquareIcon,
    title: "A customer portal that actually negotiates",
    body: "Customers comment on individual lines and counter on price from their own restricted view. Accepting a counter re-runs the governance, so terms beyond the ceiling re-enter approval automatically.",
  },
  {
    icon: BellIcon,
    title: "Deal health before it is too late",
    body: "Stalled deals, discounts far above that rep's own average, and delivery promises the fulfillment can no longer meet. Nudge the rep or escalate to their manager straight from the alert.",
  },
]

const FACTS = [
  { value: "18", label: "Screens, end to end" },
  { value: "37", label: "Tables in the model" },
  { value: "120", label: "API operations" },
  { value: "85", label: "Tests passing" },
]

const ROUTING = [
  {
    when: "Every line inside its ceiling",
    who: "Nobody",
    detail: "Approved on submission — still recorded, so the decision stays explainable.",
  },
  {
    when: "Over a ceiling, low or medium risk",
    who: "Sales Manager",
    detail: "One reviewer, with the flagged lines frozen as at that round.",
  },
  {
    when: "Over a ceiling, high risk",
    who: "Sales Manager, then Finance",
    detail: "Sequential. Finance cannot act until the manager has.",
  },
]

const ROLES = [
  {
    name: "Sales Rep",
    description: "Builds quotations, applies discounts, works the upsell panel.",
    can: ["Quote and price", "Submit for approval", "Answer the customer"],
    featured: false,
  },
  {
    name: "Sales Manager",
    description: "First-level approver, and the person watching deal health.",
    can: ["Approve, return or reject", "See every rep's pipeline", "Escalate at-risk deals"],
    featured: true,
  },
  {
    name: "Finance / Operations",
    description: "Second-level approver, and the owner of stock and money.",
    can: ["Second-level approval", "Accept or override splits", "Invoice and record payment"],
    featured: false,
  },
  {
    name: "Customer",
    description: "Reviews and negotiates from a portal, never an internal screen.",
    can: ["Comment on a line", "Counter on price", "Confirm in one click"],
    featured: false,
  },
  {
    name: "Admin",
    description: "Configures everything the rules are made of.",
    can: ["Products and price lists", "Tiers and approval chains", "Warehouses and plans"],
    featured: false,
  },
]

const FAQS = [
  {
    question: "How does a quotation get routed for approval?",
    answer:
      "Automatically, on submission. Each line is checked against the stricter of its customer tier ceiling and its product category ceiling. The worst single line and the revenue-weighted pattern across the whole order combine into one blended score, and the score is matched against the approval chains an admin has configured. A rep never asks for approval; they simply cannot avoid it.",
  },
  {
    question: "What happens when no single warehouse can cover an order?",
    answer:
      "It splits. The planner takes from the fewest warehouses it can, prefers the deeper shelf, and breaks ties on the shipping rates you entered. Anything left over becomes a real backorder with an expected date, not an error — and when that stock arrives it is folded into the shipment already planned for that warehouse.",
  },
  {
    question: "Can one order mix hardware and a subscription?",
    answer:
      "Yes, and they bill separately. One-time lines are invoiced only for units that have physically shipped, so partial delivery produces a partial invoice. Recurring lines bill on their own cycle, and a mid-cycle change is prorated for the days not yet used, with a credit note when the change is a reduction.",
  },
  {
    question: "Is the customer portal just an internal screen with a different name?",
    answer:
      "No. It is a separate route tree with its own login role, every query scoped to that customer's own company, and its own response shapes with nowhere to put cost, margin or the internal risk score. An unknown quotation id answers as not found rather than forbidden, so the portal cannot be used to discover what exists.",
  },
  {
    question: `Who can see what in ${APP_NAME}?`,
    answer:
      "A rep sees their own deals; managers, finance and admins see everything. Reading an approval is open to every internal role so a rep can watch their own quote move, but the decision itself is restricted to whichever role that step is actually waiting on. Accepting a split, shipping and recording payment belong to finance and operations.",
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
  const { isAuthenticated, landingPath } = useAuth()

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
          <p
            className="label-mono animate-rise text-muted-foreground"
            style={{ "--rise-delay": "0ms" } as React.CSSProperties}
          >
            Quotation · Approval · Fulfillment · Billing
          </p>

          <h1
            className="animate-rise mt-5 text-4xl font-semibold text-balance sm:text-5xl md:text-6xl"
            style={{ "--rise-delay": "60ms" } as React.CSSProperties}
          >
            Every deal,
            <br />
            from first touch to close.
          </h1>

          <p
            className="animate-rise mt-6 max-w-lg text-lg text-pretty text-muted-foreground"
            style={{ "--rise-delay": "120ms" } as React.CSSProperties}
          >
            A sales platform that enforces its own pricing discipline. Discounts route
            themselves for approval, stock splits across warehouses on its own, and
            customers negotiate in a portal instead of an email thread.
          </p>

          <div
            className="animate-rise mt-8 flex flex-wrap items-center gap-3"
            style={{ "--rise-delay": "180ms" } as React.CSSProperties}
          >
            <Button asChild size="lg">
              <Link to={isAuthenticated ? landingPath : "/login"}>
                {isAuthenticated ? "Open the workspace" : "Sign in"}
                <ArrowRightIcon className="size-4" />
              </Link>
            </Button>
            {!isAuthenticated && (
              <Button asChild size="lg" variant="outline">
                <Link to="/signup">Create a customer account</Link>
              </Button>
            )}
          </div>

          <p
            className="animate-rise mt-8 text-xs text-muted-foreground"
            style={{ "--rise-delay": "240ms" } as React.CSSProperties}
          >
            Sales and finance accounts are created by an administrator.
          </p>
        </div>

        {/* The proof: one quotation, checked line by line, and where it goes. */}
        <div
          className="animate-rise"
          style={{ "--rise-delay": "300ms" } as React.CSSProperties}
        >
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <DealFlowMark className="size-4 text-primary" />
              <span className="label-mono text-muted-foreground">Q-1042 · Acme Corp</span>
              <span className="ml-auto label-mono text-muted-foreground">Gold tier</span>
            </div>

            <div className="grid grid-cols-[1fr_3.5rem_3.5rem_5rem] gap-2 border-b bg-muted/40 px-4 py-2">
              {["Line", "Given", "Limit", "Status"].map((heading, index) => (
                <span
                  key={heading}
                  // Everything but the line name is right-aligned, matching the
                  // numbers and the badge beneath it.
                  className={cn(
                    "label-mono text-muted-foreground",
                    index > 0 && "text-right"
                  )}
                >
                  {heading}
                </span>
              ))}
            </div>

            <ul className="divide-y">
              {EXAMPLE_LINES.map((line) => (
                <li
                  key={line.product}
                  className={cn(
                    "grid grid-cols-[1fr_3.5rem_3.5rem_5rem] items-center gap-2 px-4 py-3",
                    line.over > 0 && "bg-red-500/[0.05]"
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {line.product}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {line.category}
                    </span>
                  </span>
                  <span className="text-right font-mono text-sm tabular-nums">
                    {line.given}
                  </span>
                  <span className="text-right font-mono text-sm tabular-nums text-muted-foreground">
                    {line.allowed}
                  </span>
                  <span
                    className={cn(
                      "justify-self-end rounded-md px-2 py-0.5 text-xs font-medium",
                      line.over > 0
                        ? "bg-red-500/15 text-red-700 dark:text-red-400"
                        : "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400"
                    )}
                  >
                    {line.over > 0 ? `+${line.over}pt` : "OK"}
                  </span>
                </li>
              ))}
            </ul>

            <div className="space-y-2 border-t bg-muted/40 px-4 py-3">
              <p className="text-sm">
                <span className="text-muted-foreground">Blended risk</span>{" "}
                <span className="font-mono font-medium tabular-nums">69.95</span>{" "}
                <span className="rounded-md bg-red-500/15 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:text-red-400">
                  HIGH
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                Routed to Sales Manager, then Finance. One line over its own limit was
                enough — the customer&apos;s Gold tier did not cover the Services ceiling.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function LandingPage() {
  const { isAuthenticated, landingPath } = useAuth()

  return (
    <>
      <SectionRail sections={SECTIONS} />
      <Hero />

      <Section id="modules">
        <SectionIntro
          eyebrow="Modules"
          title="The messy parts of B2B selling, handled"
          description="Not a quote-to-invoice form. Multi-level approvals, partial stock across warehouses, subscriptions mixed with hardware, and customers who want to negotiate — each one a real rule, not a status field."
        />

        <div className="mt-14 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((module) => (
            <div
              key={module.title}
              className="bg-card p-6 transition-colors hover:bg-muted/40"
            >
              <module.icon className="size-5 text-primary" />
              <h3 className="mt-4 text-base font-semibold">{module.title}</h3>
              <p className="mt-2 text-sm text-pretty text-muted-foreground">
                {module.body}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="governance" className="bg-muted/30">
        <div className="grid gap-14 lg:grid-cols-[1fr_1fr] lg:items-start">
          <div>
            <SectionIntro
              eyebrow="Governance"
              title="Why one good-looking quote still needs a manager"
              description="Different products carry different discretion. A Gold customer allowed 15% overall does not mean a thin-margin service line may go to 18%. Every line is checked against its own limit."
            />

            <p className="mt-6 max-w-lg text-sm text-pretty text-muted-foreground">
              And sometimes no single line looks alarming: two points over here, three
              there. The blended score weighs those by revenue, so a pattern of small
              concessions cannot slip through where one obvious breach would not.
            </p>

            <dl className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border">
              {FACTS.map((fact) => (
                <div key={fact.label} className="bg-card p-6">
                  <dt className="label-mono text-muted-foreground">{fact.label}</dt>
                  <dd className="mt-2 font-heading text-3xl font-semibold tabular-nums">
                    {fact.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="space-y-3">
            {ROUTING.map((rule) => (
              <div key={rule.when} className="rounded-xl border bg-card p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{rule.when}</p>
                  <Badge variant="outline" className="border-brass/40 text-brass">
                    {rule.who}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-pretty text-muted-foreground">
                  {rule.detail}
                </p>
              </div>
            ))}

            <p className="px-1 pt-2 text-xs text-muted-foreground">
              Chains are configuration, not code. An admin sets the score bands and the
              reviewers; a quotation already in flight keeps the chain it was routed onto.
            </p>
          </div>
        </div>
      </Section>

      <Section id="roles">
        <SectionIntro
          eyebrow="Roles"
          title="Five roles, each with a different job"
          description="Permissions follow the work rather than a tier list. A rep is never an approver of their own deal, and a customer never sees an internal screen."
        />

        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {ROLES.map((role) => (
            <div
              key={role.name}
              className={cn(
                "flex flex-col rounded-xl border bg-card p-6",
                role.featured && "border-brass/50 ring-1 ring-brass/20"
              )}
            >
              <h3 className="font-heading text-lg font-semibold">{role.name}</h3>
              <p className="mt-2 text-sm text-pretty text-muted-foreground">
                {role.description}
              </p>

              <ul className="mt-6 flex-1 space-y-3">
                {role.can.map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-sm">
                    <CheckIcon
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        role.featured ? "text-brass" : "text-primary"
                      )}
                    />
                    <span className="text-muted-foreground">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <Section id="faq" className="bg-muted/30">
        <div className="grid gap-14 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionIntro
            eyebrow="Questions"
            title="How it actually behaves"
            description="The rules behind the screens, and where the boundaries are."
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
          <DealFlowMark className="mx-auto size-8 text-primary" />
          <h2 className="mt-6 text-3xl font-semibold text-balance md:text-4xl">
            Stop finding out a deal was stuck last week
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-pretty text-muted-foreground">
            Sign in to build a quotation, watch it route itself, and follow it through
            fulfillment and billing without leaving the workspace.
          </p>
          <Button asChild size="lg" className="mt-8">
            <Link to={isAuthenticated ? landingPath : "/login"}>
              {isAuthenticated ? "Open the workspace" : "Sign in"}
              <ArrowRightIcon className="size-4" />
            </Link>
          </Button>
        </div>
      </section>
    </>
  )
}
