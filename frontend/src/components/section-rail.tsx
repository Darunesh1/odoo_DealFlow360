import { useEffect, useState } from "react"

import { cn } from "@/lib/utils"

export interface RailSection {
  id: string
  label: string
}

/**
 * Draft marks.
 *
 * A ship carries numbered marks on its bow showing how deep it sits in the
 * water. This rail does the same job for the page: each tick is a section, and
 * the marked one is where the reader currently is. It is a position indicator,
 * not an ornament, so it is hidden below 2xl, the first width where the
 * centred 6xl container leaves a clear margin for it.
 */
export function SectionRail({ sections }: { sections: RailSection[] }) {
  const [active, setActive] = useState(sections[0]?.id)

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
        if (visible) setActive(visible.target.id)
      },
      // A band across the upper middle of the viewport: a section counts as
      // current once its top third is in view.
      { rootMargin: "-25% 0px -60% 0px", threshold: 0 }
    )

    for (const section of sections) {
      const element = document.getElementById(section.id)
      if (element) observer.observe(element)
    }
    return () => observer.disconnect()
  }, [sections])

  return (
    <nav
      aria-label="Page sections"
      className="pointer-events-none fixed top-1/2 left-6 z-30 hidden -translate-y-1/2 2xl:block"
    >
      <ul className="flex flex-col gap-4">
        {sections.map((section, index) => {
          const isActive = section.id === active
          return (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="pointer-events-auto group flex items-center gap-3 rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-px transition-all duration-300",
                    isActive
                      ? "w-8 bg-primary"
                      : "w-4 bg-border group-hover:w-6 group-hover:bg-muted-foreground"
                  )}
                />
                <span
                  className={cn(
                    "label-mono transition-colors duration-300",
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground/60 group-hover:text-muted-foreground"
                  )}
                >
                  <span className="tabular-nums">
                    {String(index + 1).padStart(2, "0")}
                  </span>{" "}
                  {section.label}
                </span>
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
