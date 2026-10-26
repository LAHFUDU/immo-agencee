import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Download, Mail } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Spinner, StatCard, useToast } from "../components/ui";
import { api, download, type Page } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, money, relative } from "../lib/format";
import { useCatalog } from "../lib/hooks";
import type { Notification } from "../lib/types";
import { monthLabel } from "./Dashboard";

// ---------------------------------------------------------------- notifications

export function Notifications() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [unread, setUnread] = useState(false);
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["notifications", unread, page], queryFn: () => api<Page<Notification>>("/notifications", { query: { unread, page, page_size: 30 } }) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  const open = async (n: Notification) => {
    if (!n.is_read) {
      await api(`/notifications/${n.id}/read`, { method: "POST" });
      refresh();
    }
    if (n.link) navigate(n.link);
  };
  return (
    <>
      <PageHeader
        title="Notifications"
        actions={
          <>
            <Button variant={unread ? "primary" : "secondary"} size="sm" onClick={() => { setUnread(!unread); setPage(1); }}>
              {unread ? "Non lues" : "Toutes"}
            </Button>
            <Button variant="secondary" size="sm" icon={<CheckCheck className="h-4 w-4" />} loading={readAll.isPending} onClick={() => readAll.mutate()}>
              Tout marquer comme lu
            </Button>
          </>
        }
      />
      <Card>
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data?.items.length ? (
          <EmptyState title="Aucune notification" icon={<Bell className="h-10 w-10" />} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {q.data.items.map((n) => (
              <li key={n.id}>
                <button onClick={() => open(n)} className={`flex w-full gap-3 px-2 py-3 text-left hover:bg-slate-50 ${n.is_read ? "" : "bg-brand-50/50"}`}>
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.is_read ? "bg-transparent" : "bg-brand-600"}`} aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className={`block text-sm ${n.is_read ? "text-slate-700" : "font-semibold text-slate-900"}`}>{n.title}</span>
                    {n.body && <span className="block text-sm text-slate-500">{n.body}</span>}
                    <span className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                      {relative(n.created_at)}
                      {n.email_status === "sent" && <Badge color="green"><Mail className="h-3 w-3" /> e-mail envoyé</Badge>}
                      {n.email_status === "failed" && <Badge color="red">échec e-mail</Badge>}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------- agents

interface AgentPerf {
  agent_id: string;
  agent: string;
  active: boolean;
  requests_assigned: number;
  requests_open: number;
  requests_converted: number;
  requests_lost: number;
  conversion_rate: number | null;
  avg_first_contact_hours: number | null;
  visits_done: number;
  deals_won: number;
  deals_lost: number;
  sales_volume?: string;
  commission?: string;
  overdue_follow_ups: number;
}

export function Agents() {
  const navigate = useNavigate();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const q = useQuery({ queryKey: ["agents", from, to], queryFn: () => api<AgentPerf[]>("/agents", { query: { date_from: from, date_to: to } }) });
  return (
    <>
      <PageHeader title="Agents commerciaux" subtitle="Portefeuille et performance par agent (données réelles)." />
      <div className="mb-4 flex flex-wrap gap-3">
        <Field label="Du">{(id) => <Input id={id} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
        <Field label="Au">{(id) => <Input id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data?.length ? (
        <Card><EmptyState title="Aucun agent commercial">Créez des comptes agents dans « Utilisateurs ».</EmptyState></Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {q.data.map((a) => (
            <Card key={a.agent_id} title={<span>{a.agent}{!a.active && <Badge className="ml-2">désactivé</Badge>}</span>} actions={<Button size="sm" variant="ghost" onClick={() => navigate(`/app/requests?assigned_agent_id=${a.agent_id}&status=open`)}>Ses demandes</Button>}>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs text-slate-500">Demandes ouvertes</dt><dd className="text-lg font-semibold">{a.requests_open}</dd></div>
                <div><dt className="text-xs text-slate-500">Relances en retard</dt><dd className={`text-lg font-semibold ${a.overdue_follow_ups ? "text-red-600" : ""}`}>{a.overdue_follow_ups}</dd></div>
                <div><dt className="text-xs text-slate-500">Converties / assignées</dt><dd className="font-semibold">{a.requests_converted} / {a.requests_assigned}</dd></div>
                <div><dt className="text-xs text-slate-500">Taux de conversion</dt><dd className="font-semibold">{a.conversion_rate === null ? "—" : `${a.conversion_rate} %`}</dd></div>
                <div><dt className="text-xs text-slate-500">1er contact moyen</dt><dd className="font-semibold">{a.avg_first_contact_hours === null ? "—" : `${a.avg_first_contact_hours} h`}</dd></div>
                <div><dt className="text-xs text-slate-500">Visites effectuées</dt><dd className="font-semibold">{a.visits_done}</dd></div>
                <div><dt className="text-xs text-slate-500">Transactions conclues</dt><dd className="font-semibold">{a.deals_won}</dd></div>
                {a.commission !== undefined && <div><dt className="text-xs text-slate-500">Commissions</dt><dd className="font-semibold">{money(a.commission)}</dd></div>}
              </dl>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- reports

interface Reports {
  period: { from: string; to: string };
  requests_per_month: { month: string; count: number }[];
  inventory_available: { city: string; property_type: string; count: number }[];
  closed_per_month: { month: string; sold: number; rented: number }[];
  waiting: { count: number; by_city: { city: string; property_type: string; count: number }[]; oldest: { id: string; reference: string; customer: string; city: string; neighborhood: string | null; property_type: string; budget_max: string | null; created_at: string; agent: string | null }[] };
  avg_first_contact_hours: number | null;
  avg_deal_close_days: number | null;
  avg_request_to_close_days: number | null;
  conversion: { requests: number; converted: number; rate: number | null };
  agents: AgentPerf[];
  revenue_per_month?: { month: string; volume: string; commission: string }[];
  lost_reasons: { requests: { reason: string; count: number }[]; deals: { reason: string; count: number }[]; rejected_matches: { reason: string; count: number }[] };
}

function ExportReport({ report, from, to }: { report: string; from: string; to: string }) {
  const { can } = useAuth();
  const toast = useToast();
  if (!can("reports.export")) return null;
  return (
    <div className="flex gap-1">
      {(["csv", "xlsx"] as const).map((fmt) => (
        <Button key={fmt} size="sm" variant="ghost" icon={<Download className="h-3.5 w-3.5" />} onClick={() => download("/reports/export", { report, fmt, date_from: from, date_to: to }).catch(toast.error)}>
          {fmt.toUpperCase()}
        </Button>
      ))}
    </div>
  );
}

export function ReportsPage() {
  const { typeLabel } = useCatalog();
  const navigate = useNavigate();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const q = useQuery({ queryKey: ["reports", from, to], queryFn: () => api<Reports>("/reports", { query: { date_from: from, date_to: to } }) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const r = q.data!;
  const reasons = [...r.lost_reasons.requests.map((x) => ({ ...x, origin: "Demande" })), ...r.lost_reasons.deals.map((x) => ({ ...x, origin: "Transaction" })), ...r.lost_reasons.rejected_matches.map((x) => ({ ...x, origin: "Bien rejeté" }))];
  return (
    <>
      <PageHeader title="Rapports" subtitle={`Période du ${date(r.period.from)} au ${date(r.period.to)} — calculés sur les données réelles de la base.`} />
      <div className="mb-4 flex flex-wrap gap-3">
        <Field label="Du">{(id) => <Input id={id} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
        <Field label="Au">{(id) => <Input id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Taux de conversion" value={r.conversion.rate === null ? "—" : `${r.conversion.rate} %`} hint={`${r.conversion.converted} / ${r.conversion.requests} demandes`} tone="green" />
        <StatCard label="Délai moyen 1er contact" value={r.avg_first_contact_hours === null ? "—" : `${r.avg_first_contact_hours} h`} />
        <StatCard label="Délai moyen de conclusion" value={r.avg_deal_close_days === null ? "—" : `${r.avg_deal_close_days} j`} hint={r.avg_request_to_close_days !== null ? `${r.avg_request_to_close_days} j depuis la demande` : undefined} tone="gold" />
        <StatCard label="Clients en attente d'un bien" value={r.waiting.count} tone="red" onClick={() => navigate("/app/waiting-list")} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Nouvelles demandes par mois" actions={<ExportReport report="requests_per_month" from={from} to={to} />}>
          {r.requests_per_month.length ? (
            <div className="h-60"><ResponsiveContainer><BarChart data={r.requests_per_month.map((x) => ({ ...x, label: monthLabel(x.month) }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} width={30} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="count" name="Demandes" fill="#236662" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
          ) : <EmptyState title="Aucune donnée sur la période" />}
        </Card>
        <Card title="Biens vendus et loués par mois" actions={<ExportReport report="closed_per_month" from={from} to={to} />}>
          {r.closed_per_month.length ? (
            <div className="h-60"><ResponsiveContainer><BarChart data={r.closed_per_month.map((x) => ({ ...x, label: monthLabel(x.month) }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} width={30} tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Bar dataKey="sold" name="Ventes" stackId="a" fill="#0ea5e9" /><Bar dataKey="rented" name="Locations" stackId="a" fill="#c9a24a" /></BarChart></ResponsiveContainer></div>
          ) : <EmptyState title="Aucune transaction conclue sur la période" />}
        </Card>
        {r.revenue_per_month && (
          <Card title="Chiffre d'affaires et commissions" className="lg:col-span-2">
            {r.revenue_per_month.length ? (
              <div className="h-64"><ResponsiveContainer><LineChart data={r.revenue_per_month.map((x) => ({ label: monthLabel(x.month), volume: Number(x.volume), commission: Number(x.commission) }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 12 }} /><YAxis yAxisId="l" width={80} tick={{ fontSize: 11 }} /><YAxis yAxisId="r" orientation="right" width={70} tick={{ fontSize: 11 }} /><Tooltip formatter={(v) => money(v as number)} /><Legend /><Line yAxisId="l" dataKey="volume" name="Volume" stroke="#236662" strokeWidth={2} /><Line yAxisId="r" dataKey="commission" name="Commissions" stroke="#c9a24a" strokeWidth={2} /></LineChart></ResponsiveContainer></div>
            ) : <EmptyState title="Aucune commission sur la période" />}
          </Card>
        )}
        <Card title="Inventaire disponible par ville et type" actions={<ExportReport report="inventory_available" from={from} to={to} />}>
          <SimpleTable head={["Ville", "Type", "Disponibles"]} rows={r.inventory_available.map((x) => [x.city, typeLabel(x.property_type), x.count])} />
        </Card>
        <Card title="Demandes en attente (par ville et type)" actions={<ExportReport report="waiting" from={from} to={to} />}>
          <SimpleTable head={["Ville", "Type", "En attente"]} rows={r.waiting.by_city.map((x) => [x.city, typeLabel(x.property_type), x.count])} />
        </Card>
        <Card title="Performance des agents" className="lg:col-span-2" actions={<ExportReport report="agents" from={from} to={to} />}>
          <SimpleTable
            head={["Agent", "Assignées", "Converties", "Conversion", "1er contact", "Visites", "Conclues", ...(r.agents.some((a) => a.commission !== undefined) ? ["Commission"] : [])]}
            rows={r.agents.map((a) => [a.agent, a.requests_assigned, a.requests_converted, a.conversion_rate === null ? "—" : `${a.conversion_rate} %`, a.avg_first_contact_hours === null ? "—" : `${a.avg_first_contact_hours} h`, a.visits_done, a.deals_won, ...(a.commission !== undefined ? [money(a.commission)] : [])])}
          />
        </Card>
        <Card title="Motifs d'échec" className="lg:col-span-2" actions={<ExportReport report="lost_reasons" from={from} to={to} />}>
          <SimpleTable head={["Origine", "Motif", "Nombre"]} rows={reasons.map((x) => [x.origin, x.reason, x.count])} />
        </Card>
      </div>
    </>
  );
}

function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  if (!rows.length) return <EmptyState title="Aucune donnée" />;
  return (
    <div className="scrollbar-thin -mx-4 max-h-80 overflow-auto sm:mx-0">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-white">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">{head.map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="px-3 py-1.5">{c}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}
