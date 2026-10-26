import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, MapPin, Phone } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { VisitStatusBadge } from "../components/domain";
import { Button, Card, EmptyState, ErrorState, Field, Modal, PageHeader, Pagination, Select, Spinner, Tabs, Textarea, useToast } from "../components/ui";
import { api, type Page } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime } from "../lib/format";
import { useDirectory } from "../lib/hooks";
import { L, options } from "../lib/i18n";
import type { Task, Visit } from "../lib/types";

const today = () => new Date().toISOString().slice(0, 10);

export default function Visits() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "visits" | "tasks") ?? "visits";
  return (
    <>
      <PageHeader title="Visites & rendez-vous" subtitle="Planning des visites, tâches de suivi et rappels." />
      <Tabs value={tab} onChange={(v) => setParams({ tab: v })} tabs={[{ value: "visits", label: "Visites" }, { value: "tasks", label: "Tâches & rappels" }]} />
      {tab === "visits" ? <VisitsTab /> : <TasksTab />}
    </>
  );
}

function VisitsTab() {
  const { can } = useAuth();
  const agents = useDirectory(true);
  const [when, setWhen] = useState<"upcoming" | "past" | "all">("upcoming");
  const [status, setStatus] = useState("scheduled");
  const [agent, setAgent] = useState("");
  const [page, setPage] = useState(1);
  const [closing, setClosing] = useState<Visit | null>(null);
  const query = {
    date_from: when === "upcoming" ? today() : undefined,
    date_to: when === "past" ? today() : undefined,
    status,
    agent_id: agent,
    order: when === "past" ? "desc" : "asc",
    page,
    page_size: 20,
  };
  const q = useQuery({ queryKey: ["visits", query], queryFn: () => api<Page<Visit>>("/visits", { query }), placeholderData: (p) => p });
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Field label="Période">{(id) => <Select id={id} value={when} onChange={(e) => { setWhen(e.target.value as typeof when); setPage(1); }} options={[{ value: "upcoming", label: "À venir" }, { value: "past", label: "Passées" }, { value: "all", label: "Toutes" }]} />}</Field>
        <Field label="Statut">{(id) => <Select id={id} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} placeholder="Tous" options={options(L.visitStatus)} />}</Field>
        {can("visits.view_all") && (
          <Field label="Agent">{(id) => <Select id={id} value={agent} onChange={(e) => { setAgent(e.target.value); setPage(1); }} placeholder="Tous" options={[{ value: "me", label: "Moi" }, ...(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))]} />}</Field>
        )}
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data?.items.length ? (
        <Card>
          <EmptyState title="Aucune visite" icon={<CalendarClock className="h-10 w-10" />}>Planifiez une visite depuis une demande client, onglet « Biens correspondants ».</EmptyState>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {q.data.items.map((v) => (
            <article key={v.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-slate-900">{dateTime(v.scheduled_at)}</p>
                  <p className="text-xs text-slate-500">{v.duration_minutes} min · {v.agent?.full_name ?? "—"}</p>
                </div>
                <VisitStatusBadge s={v.status} />
              </div>
              <div className="mt-3 space-y-1 text-sm">
                <p>
                  <Link to={`/app/properties/${v.property_id}`} className="font-medium text-brand-800 hover:underline">
                    {v.property_reference} — {v.property_title}
                  </Link>
                </p>
                <p className="flex items-center gap-1 text-slate-600">
                  <MapPin className="h-3.5 w-3.5" /> {v.property_city}
                  {v.property_address ? ` · ${v.property_address}` : ""}
                </p>
                <p className="flex items-center gap-1 text-slate-600">
                  <Phone className="h-3.5 w-3.5" />
                  {v.request_id ? <Link to={`/app/requests/${v.request_id}`} className="hover:underline">{v.customer_name}</Link> : v.customer_name}
                  {v.customer_phone && <a href={`tel:${v.customer_phone}`} className="text-brand-700 hover:underline">· {v.customer_phone}</a>}
                </p>
                {v.notes && <p className="text-slate-500">{v.notes}</p>}
                {v.customer_feedback && <p className="text-slate-700">Retour : {v.customer_feedback}</p>}
              </div>
              {can("visits.manage") && v.status === "scheduled" && (
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <Button size="sm" icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => setClosing(v)}>
                    Compte rendu
                  </Button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />}
      {closing && <VisitReport visit={closing} onClose={() => setClosing(null)} />}
    </>
  );
}

function VisitReport({ visit, onClose }: { visit: Visit; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("done");
  const [feedback, setFeedback] = useState("");
  const save = useMutation({
    mutationFn: () => api(`/visits/${visit.id}`, { method: "PATCH", body: { status, customer_feedback: feedback || null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visits"] });
      toast.success("Visite mise à jour.");
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal open onClose={onClose} title="Compte rendu de visite" footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Enregistrer</Button></>}>
      <div className="space-y-3">
        <Field label="Résultat">{(id) => <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)} options={options(L.visitStatus).filter((o) => o.value !== "scheduled")} />}</Field>
        <Field label="Retour du client">{(id) => <Textarea id={id} rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}

function TasksTab() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [status, setStatus] = useState("open");
  const q = useQuery({ queryKey: ["tasks", "all-list", scope, status], queryFn: () => api<Task[]>("/tasks", { query: { scope, status } }) });
  const toggle = useMutation({
    mutationFn: (t: Task) => api(`/tasks/${t.id}`, { method: "PATCH", body: { status: t.status === "done" ? "open" : "done" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
    onError: toast.error,
  });
  return (
    <Card
      title="Tâches"
      actions={
        <>
          {can("requests.view_all") && <Select aria-label="Périmètre" value={scope} onChange={(e) => setScope(e.target.value as "mine" | "all")} options={[{ value: "mine", label: "Mes tâches" }, { value: "all", label: "Toute l'équipe" }]} />}
          <Select aria-label="Statut" value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "open", label: "À faire" }, { value: "done", label: "Terminées" }, { value: "open,done", label: "Toutes" }]} />
        </>
      }
    >
      {q.isLoading ? (
        <Spinner />
      ) : !q.data?.length ? (
        <EmptyState title="Aucune tâche">Ajoutez des tâches et rappels depuis une demande ou une fiche client.</EmptyState>
      ) : (
        <ul className="divide-y divide-slate-100">
          {q.data.map((t) => {
            const late = t.status === "open" && new Date(t.due_at) < new Date();
            return (
              <li key={t.id} className="flex items-center gap-3 py-2.5">
                <input type="checkbox" checked={t.status === "done"} onChange={() => toggle.mutate(t)} aria-label="Terminée" className="h-4 w-4 rounded border-slate-300" />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${t.status === "done" ? "text-slate-400 line-through" : "text-slate-800"}`}>{t.title}</p>
                  <p className={`text-xs ${late ? "font-medium text-red-600" : "text-slate-500"}`}>
                    {late ? "En retard · " : ""}
                    {dateTime(t.due_at)} · {t.assigned_to.full_name}
                    {t.request_id && (
                      <>
                        {" · "}
                        <Link to={`/app/requests/${t.request_id}`} className="text-brand-700 hover:underline">
                          voir la demande
                        </Link>
                      </>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
