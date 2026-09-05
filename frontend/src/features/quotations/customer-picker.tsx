import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckIcon, ChevronsUpDownIcon, UserPlusIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { api, errorMessage } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Customer } from "@/types/api"

/**
 * Search-and-pick, or add one on the spot.
 *
 * A rep should not have to stop and find an admin to quote someone new. The
 * tier is deliberately not offered: a new customer starts on the lowest
 * ceiling, and letting the person who benefits from a discount choose the
 * discount band would defeat the governance the rest of the app is built on.
 */
export function CustomerPicker({
  customers,
  value,
  onChange,
}: {
  customers: Customer[]
  value: string
  onChange: (customerId: string) => void
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")

  const selected = customers.find((customer) => customer.id === value)

  const create = useMutation({
    mutationFn: async (body: { name: string; email: string }) =>
      (await api.post<Customer>("/customers", body)).data,
    onSuccess: (customer) => {
      // Written straight into the cache: the lookup has a five-minute
      // staleTime, so a refetch would not show the new row for the rest of
      // this sitting.
      queryClient.setQueryData<Customer[]>(["lookups", "customers"], (current) =>
        current?.some((item) => item.id === customer.id)
          ? current
          : [...(current ?? []), customer]
      )
      onChange(customer.id)
      setCreating(false)
      setOpen(false)
      setName("")
      setEmail("")
      toast.success(
        `${customer.name} added on the ${customer.tier?.name ?? "lowest"} tier — they have been emailed a link to set a password.`
      )
    },
    onError: (caught) =>
      toast.error(errorMessage(caught, "Could not add that customer.")),
  })

  if (creating) {
    return (
      <div className="space-y-3 rounded-lg border p-3">
        <p className="text-sm font-medium">New customer</p>
        <div className="space-y-1.5">
          <Label>Company or person</Label>
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Zenith Co"
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="buying@zenith.example"
          />
          <p className="text-xs text-muted-foreground">
            They are emailed a link to set a password, and this quotation is
            waiting for them in the portal once they do.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setCreating(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!name.trim() || !email.trim() || create.isPending}
            onClick={() => create.mutate({ name: name.trim(), email: email.trim() })}
          >
            {create.isPending ? "Adding…" : "Add customer"}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          className="w-full justify-between font-normal"
        >
          <span className={cn("truncate", !selected && "text-muted-foreground")}>
            {selected
              ? `${selected.name}${selected.tier ? ` · ${selected.tier.name}` : ""}`
              : "Search or add a customer"}
          </span>
          <ChevronsUpDownIcon className="size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput
            placeholder="Search customers…"
            value={name}
            onValueChange={setName}
          />
          <CommandList>
            <CommandEmpty>
              <button
                type="button"
                className="w-full px-2 py-1.5 text-left text-sm hover:text-foreground"
                onClick={() => setCreating(true)}
              >
                No match. <span className="underline">Add a new customer</span>
              </button>
            </CommandEmpty>
            <CommandGroup>
              {customers.map((customer) => (
                <CommandItem
                  key={customer.id}
                  value={customer.name}
                  onSelect={() => {
                    onChange(customer.id)
                    setOpen(false)
                  }}
                >
                  <CheckIcon
                    className={cn(
                      "size-4",
                      customer.id === value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <span className="truncate">{customer.name}</span>
                  {customer.tier ? (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {customer.tier.name}
                    </span>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandGroup>
              <CommandItem onSelect={() => setCreating(true)}>
                <UserPlusIcon className="size-4" />
                Add a new customer
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
