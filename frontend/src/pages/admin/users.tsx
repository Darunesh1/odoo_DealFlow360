import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MoreHorizontalIcon,
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
import { Input } from "@/components/ui/input"
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
import type { Page, User } from "@/types/api"

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

  const setSuperuser = useMutation({
    mutationFn: async ({ id, isSuperuser }: { id: string; isSuperuser: boolean }) => {
      await api.patch(`/admin/users/${id}`, { is_superuser: isSuperuser })
    },
    onSuccess: async (_result, variables) => {
      await invalidate()
      toast.success(
        variables.isSuperuser ? "Administrator access granted." : "Administrator access removed."
      )
    },
    onError: (caught) => toast.error(errorMessage(caught, "Could not update the role.")),
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
        description="Every account on this deployment. Only administrators can see this page."
      />

      <div className="relative max-w-sm">
        <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Search by name or email"
          className="pl-9"
          aria-label="Search users"
        />
      </div>

      <Card className="overflow-hidden py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>User</TableHead>
                <TableHead className="hidden sm:table-cell">Role</TableHead>
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
                      {user.is_superuser ? (
                        <Badge variant="outline" className="gap-1 text-brass">
                          <ShieldIcon className="size-3" />
                          Admin
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">Member</span>
                      )}
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
                          <DropdownMenuItem
                            onClick={() =>
                              setSuperuser.mutate({
                                id: user.id,
                                isSuperuser: !user.is_superuser,
                              })
                            }
                          >
                            <ShieldIcon className="size-4" />
                            {user.is_superuser ? "Remove admin access" : "Make administrator"}
                          </DropdownMenuItem>
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
    </>
  )
}
