import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import {
  RequireAdmin,
  RequireAuth,
  RequireGuest,
} from "@/components/route-guards";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/features/auth/auth-context";
import { AppLayout } from "@/layouts/app-layout";
import { AuthLayout } from "@/layouts/auth-layout";
import { MarketingLayout } from "@/layouts/marketing-layout";
import { DealFlowMark } from "@/components/brand";

// Split per route: a first-time visitor loads the landing page without paying
// for the sidebar, the data table and the dialogs behind the sign-in wall.
const LandingPage = lazy(() => import("@/pages/landing"));
const LoginPage = lazy(() => import("@/pages/auth/login"));
const RegisterPage = lazy(() => import("@/pages/auth/register"));
const ForgotPasswordPage = lazy(() => import("@/pages/auth/forgot-password"));
const ResetPasswordPage = lazy(() => import("@/pages/auth/reset-password"));
const VerifyEmailPage = lazy(() => import("@/pages/auth/verify-email"));
const DashboardPage = lazy(() => import("@/pages/app/dashboard"));
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
              <Route
                path="/register"
                element={
                  <RequireGuest>
                    <RegisterPage />
                  </RequireGuest>
                }
              />
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
              <Route path="profile" element={<ProfilePage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route
                path="admin/users"
                element={
                  <RequireAdmin>
                    <AdminUsersPage />
                  </RequireAdmin>
                }
              />
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
