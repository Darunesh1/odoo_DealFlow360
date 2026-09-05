import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useQuotationLookups,
  useQuotationMutations,
} from "@/features/quotations/use-quotation"

/** Today, as the yyyy-mm-dd a date input wants. */
function today() {
  return new Date().toISOString().slice(0, 10)
}

const schema = z.object({
  customer_id: z.string().min(1, "Choose a customer"),
  currency: z.string().min(3, "Choose a currency"),
  requested_delivery_date: z
    .string()
    .min(1, "Pick a delivery date")
    .refine((value) => value >= today(), "That date has already passed"),
})

type Values = z.infer<typeof schema>

/**
 * The three things a quotation cannot be started without.
 *
 * Customer and currency decide how every line is priced - the tier ceiling and
 * the price list both hang off them. The delivery date is what the warehouse
 * split is promised against and what delivery slippage is later measured from,
 * so a quotation without one leaves both unanswerable. Everything else is
 * edited on the builder itself.
 */
export function NewQuotationDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const { customers, currencies } = useQuotationLookups()
  const { create } = useQuotationMutations(undefined)

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      customer_id: "",
      currency: "USD",
      requested_delivery_date: "",
    },
  })

  const onSubmit = async (values: Values) => {
    const quotation = await create.mutateAsync(values)
    onOpenChange(false)
    form.reset()
    navigate(`/app/quotations/${quotation.id}`)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New quotation</DialogTitle>
          <DialogDescription>
            Pick who it is for. Their tier decides the price list and the
            discount ceiling every line is measured against.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="customer_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Customer</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Choose a customer" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(customers.data ?? []).map((customer) => (
                        <SelectItem key={customer.id} value={customer.id}>
                          {customer.name}
                          {customer.tier ? ` · ${customer.tier.name}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="currency"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Currency</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Currency" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(currencies.data ?? []).map((currency) => (
                        <SelectItem key={currency.code} value={currency.code}>
                          {currency.code} · {currency.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Prices resolve from this customer&apos;s tier in this currency.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="requested_delivery_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Requested delivery date</FormLabel>
                  <FormControl>
                    <Input type="date" min={today()} {...field} />
                  </FormControl>
                  <FormDescription>
                    What the customer asked for. The split is promised against
                    it, and a promise it can no longer meet raises an alert.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "Creating…" : "Create quotation"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
