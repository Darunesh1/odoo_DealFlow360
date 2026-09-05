import { ArrowDownIcon, ArrowUpIcon, ChevronsUpDownIcon } from "lucide-react"

import { TableHead } from "@/components/ui/table"
import { cn } from "@/lib/utils"

/** A column header that sorts. The arrow only appears on the active column, so
 * the header row does not read as a wall of icons. */
export function SortableHeader<K extends string>({
  column,
  active,
  direction,
  onSort,
  className,
  children,
}: {
  column: K
  active: K
  direction: "asc" | "desc"
  onSort: (column: K) => void
  className?: string
  children: React.ReactNode
}) {
  const isActive = column === active
  const Icon = !isActive ? ChevronsUpDownIcon : direction === "asc" ? ArrowUpIcon : ArrowDownIcon
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-foreground"
        aria-label={`Sort by ${String(children)}`}
      >
        {children}
        <Icon
          className={cn("size-3", isActive ? "opacity-100" : "opacity-40")}
          aria-hidden
        />
      </button>
    </TableHead>
  )
}
