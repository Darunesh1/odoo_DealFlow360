import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { z } from "zod"

import { Button } from "@/components/ui/button"
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

const schema = z.object({
  customer_id: z.string().min(1, "Choose a customer"),
  currency: z.string().min(3, "Choose a currency"),
})

type Values = z.infer<typeof schema>

/**
 * Customer and currency are the only two things that must be settled before a
 * line can be priced - the tier ceiling and the price list both hang off them.
 * Everything else is edited on the builder itself.
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
    defaultValues: { customer_id: "", currency: "USD" },
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
