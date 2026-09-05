import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { ROLES, ROLE_LABELS, type Role } from "@/types/api"

/**
 * Role selection as checkboxes rather than a single-select: roles are additive,
 * so one person can be both a Sales Manager and Finance.
 */
export function RolePicker({
  value,
  onChange,
  disabled,
  idPrefix = "role",
}: {
  value: Role[]
  onChange: (roles: Role[]) => void
  disabled?: boolean
  idPrefix?: string
}) {
  const toggle = (role: Role, checked: boolean) =>
    onChange(checked ? [...value, role] : value.filter((r) => r !== role))

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {ROLES.map((role) => (
        <div
          key={role}
          className="flex items-center gap-2 rounded-md border p-2.5 has-[:checked]:border-primary/50 has-[:checked]:bg-primary/5"
        >
          <Checkbox
            id={`${idPrefix}-${role}`}
            checked={value.includes(role)}
            disabled={disabled}
            onCheckedChange={(checked) => toggle(role, checked === true)}
          />
          <Label htmlFor={`${idPrefix}-${role}`} className="cursor-pointer text-sm font-normal">
            {ROLE_LABELS[role]}
          </Label>
        </div>
      ))}
    </div>
  )
}

/** The role badges shown against a user in the admin table. */
export function RoleBadges({ roles }: { roles: Role[] }) {
  if (roles.length === 0) {
    return <span className="text-sm text-muted-foreground">No roles</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {roles.map((role) => (
        <span
          key={role}
          className={
            "rounded-md border px-1.5 py-0.5 text-xs font-medium " +
            (role === "admin" ? "border-brass/40 text-brass" : "text-muted-foreground")
          }
        >
          {ROLE_LABELS[role]}
        </span>
      ))}
    </div>
  )
}
