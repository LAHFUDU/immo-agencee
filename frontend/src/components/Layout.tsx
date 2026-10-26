import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BarChart3,
  Bell,
  Building2,
  CalendarClock,
  ClipboardList,
  Cog,
  Handshake,
  Hourglass,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Search,
  Shuffle,
  UserCog,
  Users,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { t } from "../lib/i18n";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  perm?: string[];
}

const NAV: NavItem[] = [
  { to: "/app", label: t("nav.dashboard"), icon: <LayoutDashboard className="h-4 w-4" />, perm: ["dashboard.view"] },
  { to: "/app/requests", label: t("nav.requests"), icon: <ClipboardList className="h-4 w-4" />, perm: ["requests.view"] },
  { to: "/app/waiting-list", label: t("nav.waiting"), icon: <Hourglass className="h-4 w-4" />, perm: ["requests.view"] },
  { to: "/app/properties", label: t("nav.properties"), icon: <Building2 className="h-4 w-4" />, perm: ["properties.view"] },
  { to: "/app/matching", label: t("nav.matching"), icon: <Shuffle className="h-4 w-4" />, perm: ["matches.view", "requests.view"] },
  { to: "/app/customers", label: t("nav.customers"), icon: <Users className="h-4 w-4" />, perm: ["customers.view"] },
  { to: "/app/visits", label: t("nav.visits"), icon: <CalendarClock className="h-4 w-4" />, perm: ["visits.view"] },
  { to: "/app/deals", label: t("nav.deals"), icon: <Handshake className="h-4 w-4" />, perm: ["deals.view"] },
  { to: "/app/agents", label: t("nav.agents"), icon: <UsersRound className="h-4 w-4" />, perm: ["agents.view"] },
  { to: "/app/notifications", label: t("nav.notifications"), icon: <Bell className="h-4 w-4" /> },
  { to: "/app/reports", label: t("nav.reports"), icon: <BarChart3 className="h-4 w-4" />, perm: ["reports.view"] },
  { to: "/app/users", label: t("nav.users"), icon: <UserCog className="h-4 w-4" />, perm: ["users.manage"] },
  { to: "/app/settings", label: t("nav.settings"), icon: <Cog className="h-4 w-4" />, perm: ["settings.manage"] },
  { to: "/app/audit", label: t("nav.audit"), icon: <ScrollText className="h-4 w-4" />, perm: ["audit.view"] },
];

function useUnread() {
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(id);
  }, [q]);
  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  type Hit = { id: string; label: string; sub: string };
  const res = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api<Record<"customers" | "requests" | "properties" | "deals", Hit[]>>("/search", { query: { q: debounced } }),
    enabled: debounced.length >= 2,
  });
  const groups: [keyof NonNullable<typeof res.data>, string, string][] = [
    ["requests", "Demandes", "/app/requests/"],
    ["customers", "Clients", "/app/customers/"],
    ["properties", "Biens", "/app/properties/"],
    ["deals", "Transactions", "/app/deals/"],
  ];
  const go = (href: string) => {
    setOpen(false);
    setQ("");
    navigate(href);
  };
  const total = res.data ? groups.reduce((n, [k]) => n + res.data![k].length, 0) : 0;
  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
      <input
        type="search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        placeholder="Nom, téléphone, référence…"
        aria-label="Recherche globale"
        className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
      {open && debounced.length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-[70vh] overflow-y-auto rounded-xl border border-slate-200 bg-white py-2 shadow-xl">
          {res.isLoading && <p className="px-4 py-2 text-sm text-slate-500">Recherche…</p>}
          {res.data && total === 0 && <p className="px-4 py-2 text-sm text-slate-500">Aucun résultat pour « {debounced} »</p>}
          {res.data &&
            groups.map(([k, label, base]) =>
              res.data![k].length ? (
                <div key={k} className="py-1">
                  <p className="px-4 py-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
                  {res.data![k].map((h) => (
                    <button key={h.id} onClick={() => go(base + h.id)} className="block w-full px-4 py-1.5 text-left hover:bg-brand-50">
                      <span className="block truncate text-sm text-slate-800">{h.label}</span>
                      <span className="block truncate text-xs text-slate-500">{h.sub}</span>
                    </button>
                  ))}
                </div>
              ) : null,
            )}
        </div>
      )}
    </div>
  );
}

export function AppLayout() {
  const { me, can, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const unread = useUnread();
  useEffect(() => setMobileOpen(false), [location.pathname]);

  const items = NAV.filter((n) => !n.perm || can(...n.perm));
  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-4" aria-label="Navigation principale">
      {items.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/app"}
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-white/10 text-white" : "text-brand-100/80 hover:bg-white/5 hover:text-white",
            )
          }
        >
          {n.icon}
          <span className="flex-1">{n.label}</span>
          {n.to === "/app/notifications" && !!unread.data?.count && (
            <span className="rounded-full bg-gold-500 px-1.5 text-xs font-semibold text-brand-950">{unread.data.count}</span>
          )}
        </NavLink>
      ))}
    </nav>
  );

  const brand = (
    <Link to="/app" className="flex items-center gap-2 px-5 py-5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gold-500 text-brand-950">
        <Building2 className="h-4 w-4" />
      </span>
      <span className="font-semibold tracking-tight text-white">Immo Agence</span>
    </Link>
  );

  const userBox = (
    <div className="border-t border-white/10 p-4">
      <p className="truncate text-sm font-medium text-white">{me?.full_name}</p>
      <p className="truncate text-xs text-brand-200">{me?.role_name}</p>
      <div className="mt-3 flex gap-2">
        <Link to="/app/account" className="rounded-md bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/20">
          Mon compte
        </Link>
        <button onClick={() => logout()} className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-brand-100 hover:bg-white/10">
          <LogOut className="h-3 w-3" /> {t("common.logout")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:pl-64">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Aller au contenu
      </a>
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col bg-brand-900 lg:flex">
        {brand}
        {nav}
        {userBox}
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-brand-900 shadow-xl">
            <button className="absolute right-3 top-5 text-brand-100" onClick={() => setMobileOpen(false)} aria-label="Fermer le menu">
              <X className="h-5 w-5" />
            </button>
            {brand}
            {nav}
            {userBox}
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-2.5 backdrop-blur sm:px-6">
        <button className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu">
          <Menu className="h-5 w-5" />
        </button>
        <GlobalSearch />
        <div className="ml-auto flex items-center gap-2">
          <Link to="/app/notifications" className="relative rounded-full p-2 text-slate-500 hover:bg-slate-100" aria-label={`Notifications (${unread.data?.count ?? 0} non lues)`}>
            <Bell className="h-5 w-5" />
            {!!unread.data?.count && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-red-500" />}
          </Link>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="mb-1 inline-block text-sm text-brand-700 hover:underline">
      ← {children}
    </Link>
  );
}
