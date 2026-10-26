import { ShieldAlert } from "lucide-react";
import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./components/Layout";
import { EmptyState, Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import { AcceptInvitePage, AccountPage, LoginPage } from "./pages/AuthPages";
import { PublicContact, PublicHome, PublicLayout, PublicPropertyPage, PublicRequest } from "./public/PublicSite";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const RequestList = lazy(() => import("./pages/requests/RequestList"));
const RequestForm = lazy(() => import("./pages/requests/RequestForm"));
const RequestDetail = lazy(() => import("./pages/requests/RequestDetail"));
const PropertyList = lazy(() => import("./pages/properties/PropertyList"));
const PropertyForm = lazy(() => import("./pages/properties/PropertyForm"));
const PropertyDetail = lazy(() => import("./pages/properties/PropertyDetail"));
const PropertyImport = lazy(() => import("./pages/properties/PropertyImport"));
const Matching = lazy(() => import("./pages/Matching"));
const CustomerList = lazy(() => import("./pages/customers/Customers").then((m) => ({ default: m.CustomerList })));
const CustomerDetail = lazy(() => import("./pages/customers/Customers").then((m) => ({ default: m.CustomerDetail })));
const Visits = lazy(() => import("./pages/Visits"));
const DealList = lazy(() => import("./pages/deals/Deals").then((m) => ({ default: m.DealList })));
const DealDetail = lazy(() => import("./pages/deals/Deals").then((m) => ({ default: m.DealDetail })));
const Agents = lazy(() => import("./pages/Insights").then((m) => ({ default: m.Agents })));
const Notifications = lazy(() => import("./pages/Insights").then((m) => ({ default: m.Notifications })));
const Reports = lazy(() => import("./pages/Insights").then((m) => ({ default: m.ReportsPage })));
const Users = lazy(() => import("./pages/admin/Users"));
const Settings = lazy(() => import("./pages/admin/Settings"));
const Audit = lazy(() => import("./pages/admin/Audit"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (me.must_change_password && location.pathname !== "/app/account") return <Navigate to="/app/account" replace />;
  return <>{children}</>;
}

/** UX guard only — every API endpoint enforces the same permissions server side. */
function Perm({ need, children }: { need: string[]; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(...need))
    return (
      <EmptyState title="Accès refusé" icon={<ShieldAlert className="h-10 w-10" />}>
        Votre rôle ne donne pas accès à cette page. <Link to="/app" className="text-brand-700 underline">Retour au tableau de bord</Link>
      </EmptyState>
    );
  return <>{children}</>;
}

const p = (need: string[], el: ReactNode) => <Perm need={need}>{el}</Perm>;

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<PublicHome />} />
          <Route path="biens/:reference" element={<PublicPropertyPage />} />
          <Route path="demande" element={<PublicRequest />} />
          <Route path="contact" element={<PublicContact />} />
        </Route>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/accept-invite" element={<AcceptInvitePage />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={p(["dashboard.view"], <Dashboard />)} />
          <Route path="account" element={<AccountPage />} />
          <Route path="requests" element={p(["requests.view"], <RequestList />)} />
          <Route path="requests/new" element={p(["requests.create"], <RequestForm />)} />
          <Route path="requests/:id" element={p(["requests.view"], <RequestDetail />)} />
          <Route path="requests/:id/edit" element={p(["requests.edit"], <RequestForm />)} />
          <Route path="waiting-list" element={p(["requests.view"], <RequestList waitingList />)} />
          <Route path="properties" element={p(["properties.view"], <PropertyList />)} />
          <Route path="properties/new" element={p(["properties.create"], <PropertyForm />)} />
          <Route path="properties/import" element={p(["properties.import"], <PropertyImport />)} />
          <Route path="properties/:id" element={p(["properties.view"], <PropertyDetail />)} />
          <Route path="properties/:id/edit" element={p(["properties.edit"], <PropertyForm />)} />
          <Route path="matching" element={p(["matches.view", "requests.view"], <Matching />)} />
          <Route path="customers" element={p(["customers.view"], <CustomerList />)} />
          <Route path="customers/:id" element={p(["customers.view"], <CustomerDetail />)} />
          <Route path="visits" element={p(["visits.view"], <Visits />)} />
          <Route path="deals" element={p(["deals.view"], <DealList />)} />
          <Route path="deals/:id" element={p(["deals.view"], <DealDetail />)} />
          <Route path="agents" element={p(["agents.view"], <Agents />)} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="reports" element={p(["reports.view"], <Reports />)} />
          <Route path="users" element={p(["users.manage"], <Users />)} />
          <Route path="settings" element={p(["settings.manage"], <Settings />)} />
          <Route path="audit" element={p(["audit.view"], <Audit />)} />
          <Route path="*" element={<EmptyState title="Page introuvable" />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
