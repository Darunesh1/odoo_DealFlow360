import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MailIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
  ShieldIcon,
  Trash2Icon,
  UserRoundCheckIcon,
  UserRoundXIcon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { initialsFor } from "@/components/nav-user"
import { PageHeader } from "@/components/page-header"
import { RoleBadges, RolePicker } from "@/components/role-picker"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/features/auth/use-auth"
import { api, errorMessage } from "@/lib/api"
import type { Message, Page, Role, User } from "@/types/api"

const PAGE_SIZE = 10

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
})

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()

  const [searchInput, setSearchInput] = useState("")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [pendingDelete, setPendingDelete] = useState<User | null>(null)
  const [inviting, setInviting] = useState(false)
  const [editingRoles, setEditingRoles] = useState<User | null>(null)

  // Debounce so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin-users", page, search],
    queryFn: async () => {
      const { data } = await api.get<Page<User>>("/admin/users", {
        params: { page, size: PAGE_SIZE, search: search || undefined },
      })
      return data
    },
    placeholderData: keepPreviousData,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["admin-users"] })

  const setActive = useMutation({
    mutationFn: async ({ id, isActive }: { id: string; isActive: boolean }) => {
      await api.patch(`/admin/users/${id}`, { is_active: isActive })
    },
    onSuccess: async (_result, variables) => {
      await invalidate()
      toast.success(variables.isActive ? "Account reactivated." : "Account deactivated.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not update the account.")),
  })

  const inviteUser = useMutation({
    mutationFn: async (body: { email: string; full_name: string; roles: Role[] }) => {
      await api.post("/admin/users", body)
    },
    onSuccess: async () => {
      await invalidate()
      setInviting(false)
      toast.success("Invitation sent. They will set their own password.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not create that user.")),
  })

  const setRoles = useMutation({
    mutationFn: async ({ id, roles }: { id: string; roles: Role[] }) => {
      await api.patch(`/admin/users/${id}`, { roles })
    },
    onSuccess: async () => {
      await invalidate()
      setEditingRoles(null)
      toast.success("Roles updated.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not update their roles.")),
  })

  const resendInvite = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post<Message>(`/admin/users/${id}/resend-invite`)
      return data
    },
    onSuccess: (data) => toast.success(data.message),
    onError: (caught) => toast.error(errorMessage(caught, "Could not resend the invitation.")),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/admin/users/${id}`)
    },
    onSuccess: async () => {
      await invalidate()
      setPendingDelete(null)
      toast.success("User deleted.")
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not delete the user.")),
  })

  const users = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Users"
        description="Every account on this deployment. There is no public signup, so accounts start here."
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-sm">
          <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search by name or email"
            className="pl-9"
            aria-label="Search users"
          />
        </div>
        <Button onClick={() => setInviting(true)}>
          <PlusIcon className="size-4" />
          Invite user
        </Button>
      </div>

      <Card className="overflow-hidden py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>User</TableHead>
                <TableHead className="hidden sm:table-cell">Roles</TableHead>
                <TableHead className="hidden sm:table-cell">Status</TableHead>
                <TableHead className="hidden md:table-cell">Joined</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={5}>
                      <Skeleton className="h-9 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {isError && (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-sm text-destructive">
                    {errorMessage(error, "Could not load users.")}
                  </TableCell>
                </TableRow>
              )}

              {!isLoading && !isError && users.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-12 text-center">
                    <p className="text-sm font-medium">No users match that search</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Try a different name or email address.
                    </p>
                  </TableCell>
                </TableRow>
              )}

              {users.map((user) => {
                const isSelf = user.id === currentUser?.id
                return (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Avatar className="size-8 rounded-md">
                          <AvatarFallback className="rounded-md bg-muted font-mono text-xs">
                            {initialsFor(user.full_name, user.email)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {user.full_name?.trim() || "—"}
                            {isSelf && (
                              <span className="ml-2 text-xs font-normal text-muted-foreground">
                                you
                              </span>
                            )}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <RoleBadges roles={user.roles} />
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      {!user.is_active ? (
                        <Badge variant="destructive">Deactivated</Badge>
                      ) : user.is_verified ? (
                        <Badge variant="secondary">Verified</Badge>
                      ) : (
                        <Badge variant="outline">Unverified</Badge>
                      )}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="font-mono text-xs text-muted-foreground">
                        {dateFormatter.format(new Date(user.created_at))}
                      </span>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={isSelf}
                            aria-label={`Actions for ${user.email}`}
                          >
                            <MoreHorizontalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-52">
                          <DropdownMenuItem
                            onClick={() =>
                              setActive.mutate({ id: user.id, isActive: !user.is_active })
                            }
                          >
                            {user.is_active ? (
                              <>
                                <UserRoundXIcon className="size-4" />
                                Deactivate account
                              </>
                            ) : (
                              <>
                                <UserRoundCheckIcon className="size-4" />
                                Reactivate account
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setEditingRoles(user)}>
                            <ShieldIcon className="size-4" />
                            Manage roles
                          </DropdownMenuItem>
                          {!user.is_verified && (
                            <DropdownMenuItem
                              onClick={() => resendInvite.mutate(user.id)}
                            >
                              <MailIcon className="size-4" />
                              Resend invitation
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={() => setPendingDelete(user)}
                          >
                            <Trash2Icon className="size-4" />
                            Delete user
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="label-mono text-muted-foreground">
          {total} {total === 1 ? "user" : "users"} · page {page} of {Math.max(totalPages, 1)}
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page <= 1}
          >
            <ChevronLeftIcon className="size-4" />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((value) => value + 1)}
            disabled={page >= totalPages}
          >
            Next
            <ChevronRightIcon className="size-4" />
          </Button>
        </div>
      </div>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this user?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes {pendingDelete?.email}. There is no way to restore
              the account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
              disabled={remove.isPending}
            >
              {remove.isPending ? "Deleting…" : "Delete user"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Mounted only while open, so each one opens from a clean slate
          without an effect resetting it. */}
      {inviting && (
        <InviteDialog
          onClose={() => setInviting(false)}
          pending={inviteUser.isPending}
          onSubmit={(body) => inviteUser.mutate(body)}
        />
      )}

      {editingRoles && (
        <RolesDialog
          user={editingRoles}
          onClose={() => setEditingRoles(null)}
          pending={setRoles.isPending}
          onSubmit={(roles) => setRoles.mutate({ id: editingRoles.id, roles })}
        />
      )}
    </>
  )
}

/** Creates an account and emails its owner a link to set their own password. */
function InviteDialog({
  onClose,
  pending,
  onSubmit,
}: {
  onClose: () => void
  pending: boolean
  onSubmit: (body: { email: string; full_name: string; roles: Role[] }) => void
}) {
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [roles, setRoles] = useState<Role[]>([])

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a user</DialogTitle>
          <DialogDescription>
            They receive an email with a link to choose their own password. Until they
            use it, the account cannot be signed into.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-name">Full name</Label>
            <Input
              id="invite-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Riya Sharma"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="riya@company.com"
            />
          </div>
          <div className="space-y-2">
            <Label>Roles</Label>
            <RolePicker value={roles} onChange={setRoles} idPrefix="invite" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => onSubmit({ email, full_name: fullName, roles })}
            disabled={pending || !email.trim() || !fullName.trim() || roles.length === 0}
          >
            {pending ? "Sending…" : "Send invitation"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Replaces a user's roles wholesale, matching how the API treats the field. */
function RolesDialog({
  user,
  onClose,
  pending,
  onSubmit,
}: {
  user: User
  onClose: () => void
  pending: boolean
  onSubmit: (roles: Role[]) => void
}) {
  const [roles, setRoles] = useState<Role[]>(user.roles)

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Roles for {user.full_name || user.email}</DialogTitle>
          <DialogDescription>
            Roles are additive: someone can approve as a Sales Manager and handle
            Finance decisions at the same time.
          </DialogDescription>
        </DialogHeader>

        <RolePicker value={roles} onChange={setRoles} idPrefix="edit" />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onSubmit(roles)} disabled={pending || roles.length === 0}>
            {pending ? "Saving…" : "Save roles"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
