import { useQuery } from "@tanstack/react-query";
import { AlarmClock, Building2, CalendarClock, CheckCircle2, ClipboardList, Coins, Handshake, Hourglass, PhoneCall, Shuffle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, EmptyState, ErrorState, PageHeader, Spinner, StatCard } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, money } from "../lib/format";
import { L } from "../lib/i18n";

interface AgentRow {
  agent_id: string;
  agent: string;
  active: boolean;
  requests_assigned: number;
  requests_open: number;
  requests_converted: number;
  conversion_rate: number | null;
  avg_first_contact_hours: number | null;
  visits_done: number;
  deals_won: number;
  commission?: string;
}

interface Dash {
  scope: "all" | "mine";
  properties?: { total: number; available: number; sold_or_rented: number; under_negotiation: number; by_status: Record<string, number> };
  requests?: { total: number; open: number; awaiting_contact: number; unassigned: number; waiting_no_match: number; with_matches: number; overdue_follow_up: number; converted: number };
  requests_per_month?: { month: string; count: number }[];
  visits_scheduled?: number;
  upcoming_visits?: { id: string; scheduled_at: string; property: string; customer: string; agent: string | null }[];
  deals?: { won: number; active: number };
  revenue?: { year: number; volume: string; commission: string };
  tasks: { overdue: number; today: number };
  agents?: AgentRow[];
}

const STATUS_COLORS: Record<string, string> = {
  available: "#10b981", reserved: "#f59e0b", under_negotiation: "#8b5cf6", sold: "#0ea5e9", rented: "#38bdf8", unavailable: "#94a3b8", archived: "#cbd5e1",
};
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
export const monthLabel = (m: string) => {
  const [y, mm] = m.split("-");
  return `${MONTHS[Number(mm) - 1]} ${y.slice(2)}`;
};

export default function Dashboard() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/dashboard"), refetchInterval: 60_000 });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const pieData = d.properties ? Object.entries(d.properties.by_status).filter(([k, v]) => v > 0 && k !== "archived").map(([k, v]) => ({ name: L.propertyStatus[k], key: k, value: v })) : [];

  return (
    <>
      <PageHeader
        title={`Bonjour ${me?.full_name.split(" ")[0] ?? ""}`}
        subtitle={d.scope === "mine" ? "Vue de votre portefeuille (demandes qui vous sont assignées)" : "Vue d'ensemble de l'agence"}
      />

      {(d.tasks.overdue > 0 || (d.requests?.overdue_follow_up ?? 0) > 0) && (
        <div className="mb-4 flex flex-wrap gap-2">
          {d.requests && d.requests.overdue_follow_up > 0 && (
            <Link to="/app/requests?overdue=true" className="inline-flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700 ring-1 ring-red-200 hover:bg-red-100">
              <AlarmClock className="h-4 w-4" /> {d.requests.overdue_follow_up} relance(s) en retard
            </Link>
          )}
          {d.tasks.overdue > 0 && (
            <Link to="/app/visits?tab=tasks" className="inline-flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100">
              <AlarmClock className="h-4 w-4" /> {d.tasks.overdue} tâche(s) en retard
            </Link>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {d.properties && (
          <>
            <StatCard label="Biens en inventaire" value={d.properties.total} icon={<Building2 className="h-5 w-5" />} onClick={() => navigate("/app/properties")} />
            <StatCard label="Biens disponibles" value={d.properties.available} tone="green" icon={<CheckCircle2 className="h-5 w-5" />} onClick={() => navigate("/app/properties?status=available")} />
            <StatCard label="Vendus ou loués" value={d.properties.sold_or_rented} tone="slate" icon={<Handshake className="h-5 w-5" />} onClick={() => navigate("/app/properties?status=sold,rented")} />
            <StatCard label="En négociation / réservés" value={d.properties.under_negotiation} tone="gold" icon={<Handshake className="h-5 w-5" />} onClick={() => navigate("/app/properties?status=under_negotiation,reserved")} />
          </>
        )}
        {d.requests && (
          <>
            <StatCard label="Demandes clients" value={d.requests.total} hint={`${d.requests.open} ouvertes`} icon={<ClipboardList className="h-5 w-5" />} onClick={() => navigate("/app/requests")} />
            <StatCard label="À contacter" value={d.requests.awaiting_contact} hint={d.scope === "all" ? `${d.requests.unassigned} non assignées` : undefined} tone="gold" icon={<PhoneCall className="h-5 w-5" />} onClick={() => navigate("/app/requests?status=new,to_contact")} />
            <StatCard label="Clients sans bien correspondant" value={d.requests.waiting_no_match} tone="red" icon={<Hourglass className="h-5 w-5" />} onClick={() => navigate("/app/waiting-list")} />
            <StatCard label="Demandes avec correspondances" value={d.requests.with_matches} tone="green" icon={<Shuffle className="h-5 w-5" />} onClick={() => navigate("/app/requests?waiting=false&status=open")} />
          </>
        )}
        {d.visits_scheduled !== undefined && <StatCard label="Visites planifiées" value={d.visits_scheduled} icon={<CalendarClock className="h-5 w-5" />} onClick={() => navigate("/app/visits")} />}
        {d.deals && <StatCard label="Transactions conclues" value={d.deals.won} hint={`${d.deals.active} en cours`} tone="green" icon={<Handshake className="h-5 w-5" />} onClick={() => navigate("/app/deals")} />}
        {d.revenue && <StatCard label={`Commissions ${d.revenue.year}`} value={money(d.revenue.commission)} hint={`Volume : ${money(d.revenue.volume)}`} tone="gold" icon={<Coins className="h-5 w-5" />} />}
        <StatCard label="Mes tâches du jour" value={d.tasks.today} hint={d.tasks.overdue ? `${d.tasks.overdue} en retard` : "Aucun retard"} tone={d.tasks.overdue ? "red" : "slate"} icon={<AlarmClock className="h-5 w-5" />} onClick={() => navigate("/app/visits?tab=tasks")} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {d.requests_per_month && (
          <Card title="Nouvelles demandes par mois" className="lg:col-span-2">
            {d.requests_per_month.length ? (
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={d.requests_per_month.map((r) => ({ ...r, label: monthLabel(r.month) }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={32} />
                    <Tooltip formatter={(v) => [v, "Demandes"]} />
                    <Bar dataKey="count" fill="#236662" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState title="Pas encore de demandes" />
            )}
          </Card>
        )}
        {d.properties && (
          <Card title="Inventaire par statut">
            {pieData.length ? (
              <div className="h-64">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                      {pieData.map((p) => (
                        <Cell key={p.key} fill={STATUS_COLORS[p.key]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <ul className="-mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-slate-600">
                  {pieData.map((p) => (
                    <li key={p.key} className="flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLORS[p.key] }} /> {p.name} ({p.value})
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <EmptyState title="Aucun bien" />
            )}
          </Card>
        )}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {d.upcoming_visits && (
          <Card title="Prochaines visites" actions={<Link to="/app/visits" className="text-xs text-brand-700 hover:underline">Tout voir</Link>}>
            {d.upcoming_visits.length ? (
              <ul className="divide-y divide-slate-100">
                {d.upcoming_visits.map((v) => (
                  <li key={v.id} className="py-2 text-sm">
                    <p className="font-medium text-slate-800">{dateTime(v.scheduled_at)}</p>
                    <p className="text-slate-500">
                      {v.property} · {v.customer}
                      {v.agent ? ` · ${v.agent}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Aucune visite à venir" />
            )}
          </Card>
        )}
        {d.agents && (
          <Card title="Performance des agents" className="lg:col-span-2" actions={<Link to="/app/agents" className="text-xs text-brand-700 hover:underline">Détails</Link>}>
            <div className="scrollbar-thin -mx-4 overflow-x-auto sm:mx-0">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2">Agent</th>
                    <th className="px-3 py-2">Ouvertes</th>
                    <th className="px-3 py-2">Converties</th>
                    <th className="px-3 py-2">Conversion</th>
                    <th className="px-3 py-2">Visites</th>
                    <th className="px-3 py-2">Ventes/locations</th>
                    {d.agents.some((a) => a.commission !== undefined) && <th className="px-3 py-2">Commission</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.agents.filter((a) => a.active).map((a) => (
                    <tr key={a.agent_id}>
                      <td className="px-3 py-2 font-medium">{a.agent}</td>
                      <td className="px-3 py-2">{a.requests_open}</td>
                      <td className="px-3 py-2">{a.requests_converted}</td>
                      <td className="px-3 py-2">{a.conversion_rate === null ? "—" : `${a.conversion_rate} %`}</td>
                      <td className="px-3 py-2">{a.visits_done}</td>
                      <td className="px-3 py-2">{a.deals_won}</td>
                      {a.commission !== undefined && <td className="px-3 py-2">{money(a.commission)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
