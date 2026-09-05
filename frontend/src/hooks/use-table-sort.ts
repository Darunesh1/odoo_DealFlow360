import { useMemo, useState } from "react"

export type SortDirection = "asc" | "desc"

/** Sorts a fetched list client-side. For lists small enough to hold whole —
 * the paginated product catalog sorts on the server instead. */
export function useTableSort<T>(
  rows: T[],
  initialKey: keyof T & string,
  initialDirection: SortDirection = "asc"
) {
  const [key, setKey] = useState<keyof T & string>(initialKey)
  const [direction, setDirection] = useState<SortDirection>(initialDirection)

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const left = a[key]
      const right = b[key]
      if (left == null && right == null) return 0
      // Blanks sort last whichever way the column is pointing, so an
      // unpriced row never leads a "most expensive first" view.
      if (left == null) return 1
      if (right == null) return -1
      const result =
        typeof left === "number" && typeof right === "number"
          ? left - right
          : String(left).localeCompare(String(right), undefined, { numeric: true })
      return direction === "asc" ? result : -result
    })
    return copy
  }, [rows, key, direction])

  const toggle = (next: keyof T & string) => {
    if (next === key) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"))
      return
    }
    setKey(next)
    setDirection("asc")
  }

  return { sorted, sortKey: key, direction, toggle }
}
