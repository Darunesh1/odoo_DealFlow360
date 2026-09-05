import { useEffect, useState } from "react"

/**
 * Delays a value until it stops changing.
 *
 * Search boxes hit a paginated endpoint on every keystroke otherwise; 300ms is
 * long enough to swallow typing and short enough not to feel laggy.
 */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
