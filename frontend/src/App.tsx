import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import {
  RequireAdmin,
  RequireAuth,
  RequireGuest,
  RequireRole,
} from "@/components/route-guards";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/features/auth/auth-context";
import { AppLayout } from "@/layouts/app-layout";
import { PortalLayout } from "@/layouts/portal-layout";
import { AuthLayout } from "@/layouts/auth-layout";
import { MarketingLayout } from "@/layouts/marketing-layout";
import { DealFlowMark } from "@/components/brand";

// Split per route: a first-time visitor loads the landing page without paying
// for the sidebar, the data table and the dialogs behind the sign-in wall.
const LandingPage = lazy(() => import("@/pages/landing"));
const LoginPage = lazy(() => import("@/pages/auth/login"));
const SignupPage = lazy(() => import("@/pages/auth/signup"));
const AcceptInvitePage = lazy(() => import("@/pages/auth/accept-invite"));
const ForgotPasswordPage = lazy(() => import("@/pages/auth/forgot-password"));
const ResetPasswordPage = lazy(() => import("@/pages/auth/reset-password"));
const VerifyEmailPage = lazy(() => import("@/pages/auth/verify-email"));
const DashboardPage = lazy(() => import("@/pages/app/dashboard"));
const QuotationsPage = lazy(() => import("@/pages/app/quotations"));
const QuotationDetailPage = lazy(() => import("@/pages/app/quotation-detail"));
const PipelinePage = lazy(() => import("@/pages/app/pipeline"));
const ApprovalsPage = lazy(() => import("@/pages/app/approvals"));
const ApprovalDetailPage = lazy(() => import("@/pages/app/approval-detail"));
const FulfillmentPage = lazy(() => import("@/pages/app/fulfillment"));
const FulfillmentDetailPage = lazy(
  () => import("@/pages/app/fulfillment-detail")
);
const SubscriptionsPage = lazy(() => import("@/pages/app/subscriptions"));
const BillingDetailPage = lazy(() => import("@/pages/app/billing-detail"));
const InvoicesPage = lazy(() => import("@/pages/app/invoices"));
const InvoiceDetailPage = lazy(() => import("@/pages/app/invoice-detail"));
const CreditNotesPage = lazy(() => import("@/pages/app/credit-notes"));
const PortalQuotationsPage = lazy(() => import("@/pages/portal/quotations"));
const PortalQuotationDetailPage = lazy(
  () => import("@/pages/portal/quotation-detail")
);
const PortalInvoicesPage = lazy(() => import("@/pages/portal/invoices"));
const DealHealthPage = lazy(() => import("@/pages/app/deal-health"));
const ReportsPage = lazy(() => import("@/pages/app/reports"));
const AdminManagementLayout = lazy(() => import("@/pages/admin/management/layout"));
const AdminProductsPage = lazy(() => import("@/pages/admin/management/products"));
const AdminProductDetailPage = lazy(
  () => import("@/pages/admin/management/product-detail")
);
const AdminPriceListsPage = lazy(() => import("@/pages/admin/management/price-lists"));
const AdminDiscountTiersPage = lazy(
  () => import("@/pages/admin/management/discount-tiers")
);
const AdminWarehousesPage = lazy(() => import("@/pages/admin/management/warehouses"));
const AdminSubscriptionPlansPage = lazy(
  () => import("@/pages/admin/management/subscription-plans")
);
const ProductsPage = lazy(() => import("@/pages/admin/management/products"));
const ProductDetailPage = lazy(
  () => import("@/pages/admin/management/product-detail")
);
const WarehousesPage = lazy(() => import("@/pages/admin/management/warehouses"));
const ProfilePage = lazy(() => import("@/pages/app/profile"));
const SettingsPage = lazy(() => import("@/pages/app/settings"));
const AdminUsersPage = lazy(() => import("@/pages/admin/users"));
const NotFoundPage = lazy(() => import("@/pages/not-found"));

function RouteFallback() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <DealFlowMark className="size-7 animate-pulse text-muted-foreground" />
      <span className="sr-only">Loading</span>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            {/* Public marketing site */}
            <Route element={<MarketingLayout />}>
              <Route path="/" element={<LandingPage />} />
            </Route>

            {/* Signing in and account recovery */}
            <Route element={<AuthLayout />}>
              <Route
                path="/login"
                element={
                  <RequireGuest>
                    <LoginPage />
                  </RequireGuest>
                }
              />
              {/* Public sign-up is for customers only; the backend forces the
                  role. Internal staff are still created by an administrator
                  and arrive through an invitation link. */}
              <Route
                path="/signup"
                element={
                  <RequireGuest>
                    <SignupPage />
                  </RequireGuest>
                }
              />
              <Route path="/accept-invite" element={<AcceptInvitePage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              {/* Reachable while signed in: a new email address needs confirming too. */}
              <Route path="/verify-email" element={<VerifyEmailPage />} />
            </Route>

            {/* The application itself */}
            <Route
              path="/app"
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route
                path="quotations"
                element={
                  <RequireRole roles={["admin", "sales_rep", "sales_manager"]}>
                    <QuotationsPage />
                  </RequireRole>
                }
              />
              <Route
                path="quotations/:quotationId"
                element={
                  <RequireRole roles={["admin", "sales_rep", "sales_manager"]}>
                    <QuotationDetailPage />
                  </RequireRole>
                }
              />
              <Route
                path="pipeline"
                element={
                  <RequireRole roles={["admin", "sales_rep", "sales_manager"]}>
                    <PipelinePage />
                  </RequireRole>
                }
              />
              {/* Approvals are visible to every internal role - a rep must be
                  able to watch their own quote move - but only the role a step
                  is waiting on can decide it, which the service enforces. */}
              <Route
                path="approvals"
                element={
                  <RequireRole
                    roles={["admin", "sales_rep", "sales_manager", "finance"]}
                  >
                    <ApprovalsPage />
                  </RequireRole>
                }
              />
              <Route
                path="approvals/:approvalId"
                element={
                  <RequireRole
                    roles={["admin", "sales_rep", "sales_manager", "finance"]}
                  >
                    <ApprovalDetailPage />
                  </RequireRole>
                }
              />
              {/* Fulfillment is readable by every internal role; accepting a
                  split, overriding it and shipping belong to Finance and
                  Operations, guarded on the routes themselves. */}
              <Route
                path="fulfillment"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <FulfillmentPage />
                  </RequireRole>
                }
              />
              <Route
                path="fulfillment/:fulfillmentId"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <FulfillmentDetailPage />
                  </RequireRole>
                }
              />
              {/* Billing: Finance writes, sales roles read so a rep can answer
                  "has my customer been invoiced yet?" without asking. */}
              <Route
                path="subscriptions"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <SubscriptionsPage />
                  </RequireRole>
                }
              />
              <Route
                path="subscriptions/:subscriptionId"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <BillingDetailPage />
                  </RequireRole>
                }
              />
              <Route
                path="credit-notes"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <CreditNotesPage />
                  </RequireRole>
                }
              />
              <Route
                path="invoices"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <InvoicesPage />
                  </RequireRole>
                }
              />
              <Route
                path="invoices/:invoiceId"
                element={
                  <RequireRole
                    roles={["admin", "finance", "sales_manager", "sales_rep"]}
                  >
                    <InvoiceDetailPage />
                  </RequireRole>
                }
              />
              <Route
                path="deal-health"
                element={
                  <RequireRole
                    roles={["admin", "sales_rep", "sales_manager", "finance"]}
                  >
                    <DealHealthPage />
                  </RequireRole>
                }
              />
              <Route
                path="reports"
                element={
                  <RequireRole
                    roles={["admin", "sales_rep", "sales_manager", "finance"]}
                  >
                    <ReportsPage />
                  </RequireRole>
                }
              />
              {/* The same catalog screens as Admin Management, read-only, for
                  the roles that need to see what is sellable but configure
                  nothing. Admin reaches them through Admin Management instead. */}
              <Route
                path="products"
                element={
                  <RequireRole roles={["sales_rep", "sales_manager", "finance"]}>
                    <ProductsPage readOnly />
                  </RequireRole>
                }
              />
              <Route
                path="products/:productId"
                element={
                  <RequireRole roles={["sales_rep", "sales_manager", "finance"]}>
                    <ProductDetailPage readOnly />
                  </RequireRole>
                }
              />
              {/* Finance / Operations manages warehouses, per the spec. */}
              <Route
                path="warehouses"
                element={
                  <RequireRole roles={["finance"]}>
                    <WarehousesPage />
                  </RequireRole>
                }
              />
              <Route path="profile" element={<ProfilePage />} />
              <Route path="settings" element={<SettingsPage />} />
              {/* Admin Management: one tabbed area, admin-only at the parent
                  so no child route can be reached without the role. */}
              <Route
                path="admin"
                element={
                  <RequireAdmin>
                    <AdminManagementLayout />
                  </RequireAdmin>
                }
              >
                <Route index element={<Navigate to="/app/admin/products" replace />} />
                <Route path="products" element={<AdminProductsPage />} />
                <Route path="products/new" element={<AdminProductDetailPage />} />
                <Route path="products/:productId" element={<AdminProductDetailPage />} />
                <Route path="price-lists" element={<AdminPriceListsPage />} />
                <Route path="discount-tiers" element={<AdminDiscountTiersPage />} />
                <Route path="warehouses" element={<AdminWarehousesPage />} />
                <Route
                  path="subscription-plans"
                  element={<AdminSubscriptionPlansPage />}
                />
              </Route>
              <Route
                path="admin/users"
                element={
                  <RequireAdmin>
                    <AdminUsersPage />
                  </RequireAdmin>
                }
              />
            </Route>

            {/* The customer portal. Its own layout and its own route tree,
                because the spec requires a real separate restricted view
                rather than an internal screen with a different label. */}
            <Route
              path="/portal"
              element={
                <RequireRole roles={["customer"]}>
                  <PortalLayout />
                </RequireRole>
              }
            >
              <Route index element={<PortalQuotationsPage />} />
              <Route
                path="quotations/:quotationId"
                element={<PortalQuotationDetailPage />}
              />
              <Route path="invoices" element={<PortalInvoicesPage />} />
              <Route path="profile" element={<ProfilePage />} />
            </Route>

            <Route path="/dashboard" element={<Navigate to="/app" replace />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>

        <Toaster position="bottom-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}
