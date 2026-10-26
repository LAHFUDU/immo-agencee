import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Building2, CalendarPlus, Check, CheckCircle2, Handshake, Pencil, RefreshCw, Send, ThumbsUp, UserPlus, X, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { FeatureList, MatchBadge, PriorityBadge, ReasonModal, RequestStatusBadge, ScoreBar, VisitStatusBadge } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Badge, Button, Card, Checkbox, EmptyState, ErrorState, Field, Input, KV, Modal, PageHeader, Select, Spinner, Tabs, Textarea, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, fromLocalInput, money, num, range, relative } from "../../lib/format";
import { useCatalog, useDirectory } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Activity, CustomerRequest, Match, Task, Visit } from "../../lib/types";

export default function RequestDetail() {
  const { id } = useParams();
  const { can, me } = useAuth();
  const location = useLocation();
  const created = (location.state as { created?: string; matchCount?: number } | null) ?? null;
  const [tab, setTab] = useState<"matches" | "followup" | "tasks" | "visits" | "details">("matches");
  const qc = useQueryClient();
  const toast = useToast();
  const { typeLabel } = useCatalog();
  const r = useQuery({ queryKey: ["request", id], queryFn: () => api<CustomerRequest>(`/requests/${id}`) });
  const [statusOpen, setStatusOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["request", id] });
    qc.invalidateQueries({ queryKey: ["request-matches", id] });
    qc.invalidateQueries({ queryKey: ["activities", "request", id] });
    qc.invalidateQueries({ queryKey: ["requests"] });
  };
  const claim = useMutation({
    mutationFn: () => api(`/requests/${id}/claim`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      toast.success("Demande prise en charge.");
    },
    onError: toast.error,
  });

  if (r.isLoading) return <Spinner />;
  if (r.error) return <ErrorState error={r.error} />;
  const req = r.data!;
  const closed = ["converted", "closed_lost", "archived"].includes(req.status);

  return (
    <>
      <PageHeader
        back={<BackLink to="/app/requests">Demandes</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-2">
            {req.customer.full_name} <RequestStatusBadge s={req.status} /> <PriorityBadge s={req.priority} />
          </span>
        }
        subtitle={
          <>
            {req.reference} · {typeLabel(req.property_type)} ({L.transactionWish[req.transaction_type]}) · {req.city}
            {req.neighborhood ? ` / ${req.neighborhood}` : ""} · créée {relative(req.created_at)}
          </>
        }
        actions={
          <>
            {!req.assigned_agent && can("requests.edit") && !can("requests.assign") && (
              <Button variant="gold" icon={<UserPlus className="h-4 w-4" />} loading={claim.isPending} onClick={() => claim.mutate()}>
                Prendre en charge
              </Button>
            )}
            {can("requests.assign") && (
              <Button variant="secondary" icon={<UserPlus className="h-4 w-4" />} onClick={() => setAssignOpen(true)}>
                {req.assigned_agent ? "Réassigner" : "Assigner"}
              </Button>
            )}
            {can("requests.edit") && (
              <>
                <Button variant="secondary" onClick={() => setStatusOpen(true)}>
                  Changer le statut
                </Button>
                <Link to={`/app/requests/${id}/edit`}>
                  <Button variant="secondary" icon={<Pencil className="h-4 w-4" />}>
                    Modifier
                  </Button>
                </Link>
              </>
            )}
          </>
        }
      />
      {created?.created && (
        <div className="mb-4">
          <Alert color={created.matchCount ? "green" : "amber"} title={created.matchCount ? "Demande enregistrée" : "Demande enregistrée — aucun bien disponible"}>
            {created.created}
          </Alert>
        </div>
      )}

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <Card>
          <KV
            cols={1}
            items={[
              ["Client", <Link key="c" to={`/app/customers/${req.customer.id}`} className="text-brand-700 hover:underline">{req.customer.full_name} ({req.customer.reference})</Link>],
              ["Contact", <span key="p">{req.customer.phone ?? "—"} · {req.customer.email ?? "—"} <span className="text-slate-500">(préférence : {L.contactMethod[req.customer.preferred_contact]})</span></span>],
            ]}
          />
        </Card>
        <Card>
          <KV cols={1} items={[["Budget", range(req.budget_min, req.budget_max, (v) => money(v, req.currency))], ["Surface", range(req.surface_min, req.surface_max, (v) => num(v, " m²"))]]} />
        </Card>
        <Card>
          <KV
            cols={1}
            items={[
              ["Agent", req.assigned_agent?.full_name ?? <span className="text-amber-700">Non assignée</span>],
              ["Prochaine relance", req.next_follow_up_at ? <span className={new Date(req.next_follow_up_at) < new Date() && !closed ? "font-medium text-red-600" : ""}>{dateTime(req.next_follow_up_at)}</span> : "—"],
            ]}
          />
        </Card>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "matches", label: `Biens correspondants (${req.matches.active_count})` },
          { value: "followup", label: "Suivi & historique" },
          { value: "tasks", label: "Tâches" },
          { value: "visits", label: "Visites" },
          { value: "details", label: "Critères détaillés" },
        ]}
      />
      {tab === "matches" && <MatchesTab req={req} closed={closed} />}
      {tab === "followup" && <ActivitiesPanel scope="request" id={req.id} canAdd={can("requests.edit")} />}
      {tab === "tasks" && <TasksPanel requestId={req.id} />}
      {tab === "visits" && <VisitsPanel req={req} />}
      {tab === "details" && (
        <Card>
          <KV
            items={[
              ["Type", typeLabel(req.property_type)],
              ["Transaction", L.transactionWish[req.transaction_type]],
              ["Ville / quartier(s)", `${req.city}${req.neighborhood ? " / " + req.neighborhood : ""}`],
              ["Chambres min.", req.bedrooms_min ?? "—"],
              ["Salles de bain min.", req.bathrooms_min ?? "—"],
              ["Équipements obligatoires", <FeatureList key="r" codes={req.required_features} />],
              ["Équipements souhaités", <FeatureList key="p" codes={req.preferred_features} />],
              ["Source", L.source[req.source]],
              ["Premier contact", dateTime(req.first_contacted_at)],
              ["Commentaires client", req.comments ?? "—"],
              ["Notes internes", req.internal_notes ?? "—"],
              ["Motif de clôture", req.close_reason ?? "—"],
            ]}
          />
        </Card>
      )}

      <StatusModal open={statusOpen} onClose={() => setStatusOpen(false)} req={req} onDone={refresh} canArchive={can("requests.archive")} />
      <AssignModal open={assignOpen} onClose={() => setAssignOpen(false)} req={req} onDone={refresh} meId={me?.id} />
    </>
  );
}

// ---------------------------------------------------------------- matches

function MatchesTab({ req, closed }: { req: CustomerRequest; closed: boolean }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [showInactive, setShowInactive] = useState(false);
  const [showNear, setShowNear] = useState(false);
  const [rejecting, setRejecting] = useState<Match | null>(null);
  const [visitFor, setVisitFor] = useState<Match | null>(null);
  const q = useQuery({
    queryKey: ["request-matches", req.id, showInactive, showNear],
    queryFn: () => api<Match[]>(`/requests/${req.id}/matches`, { query: { include_inactive: showInactive, include_near_misses: showNear } }),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["request-matches", req.id] });
    qc.invalidateQueries({ queryKey: ["request", req.id] });
    qc.invalidateQueries({ queryKey: ["activities", "request", req.id] });
  };
  const act = useMutation({
    mutationFn: (v: { id: string; status: string; rejection_reason?: string; customer_feedback?: string }) => api(`/matches/${v.id}`, { method: "PATCH", body: v }),
    onSuccess: () => {
      invalidate();
      toast.success("Correspondance mise à jour.");
    },
    onError: toast.error,
  });
  const rematch = useMutation({
    mutationFn: () => api(`/requests/${req.id}/rematch`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      toast.success("Recherche relancée sur tout l'inventaire.");
    },
    onError: toast.error,
  });
  const renotify = useMutation({
    mutationFn: (mid: string) => api(`/matches/${mid}/renotify`, { method: "POST" }),
    onSuccess: () => toast.success("Notification renvoyée à l'agent."),
    onError: toast.error,
  });
  const deal = useMutation({
    mutationFn: (m: Match) => api<{ id: string }>("/deals", { body: { request_id: req.id, property_id: m.property_id } }),
    onSuccess: (d) => navigate(`/app/deals/${d.id}`),
    onError: toast.error,
  });
  const manage = can("matches.manage") && !closed;

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-4">
        <Checkbox label="Afficher l'historique (biens devenus indisponibles)" checked={showInactive} onChange={setShowInactive} />
        <Checkbox label="Afficher les biens proches mais non conformes" checked={showNear} onChange={setShowNear} />
        <Button variant="secondary" size="sm" icon={<RefreshCw className="h-4 w-4" />} loading={rematch.isPending} onClick={() => rematch.mutate()} className="ml-auto">
          Relancer la recherche
        </Button>
      </div>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data?.length ? (
        <Card>
          <EmptyState title="Aucun bien correspondant pour le moment" icon={<Building2 className="h-10 w-10" />}>
            La demande reste en liste d'attente. Dès qu'un bien correspondant est ajouté ou modifié, il apparaît ici et l'agent assigné est notifié.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {q.data.map((m) => (
            <article key={`${m.property_id}`} className={`rounded-xl border bg-white p-4 shadow-sm ${m.category === "ineligible" || !m.is_active ? "border-dashed border-slate-300 opacity-90" : "border-slate-200"}`}>
              <div className="flex gap-3">
                {m.property_photo ? (
                  <img src={m.property_photo} alt="" className="h-20 w-24 shrink-0 rounded-lg object-cover" loading="lazy" />
                ) : (
                  <div className="flex h-20 w-24 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-300">
                    <Building2 className="h-8 w-8" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <MatchBadge category={m.category} />
                    {m.status && m.status !== "suggested" && <Badge color={m.status === "rejected" ? "red" : "violet"}>{L.matchStatus[m.status]}</Badge>}
                    {!m.is_active && m.category !== "ineligible" && <Badge>Plus disponible ({L.propertyStatus[m.property_status]})</Badge>}
                  </div>
                  <Link to={`/app/properties/${m.property_id}`} className="mt-1 block truncate font-medium text-slate-900 hover:text-brand-700">
                    {m.property_reference} — {m.property_title}
                  </Link>
                  <p className="text-sm text-slate-500">
                    {m.property_city}
                    {m.property_neighborhood ? ` / ${m.property_neighborhood}` : ""} · {money(m.property_price, m.property_currency)} · {num(m.property_surface, " m²")}
                  </p>
                  {m.category !== "ineligible" && (
                    <div className="mt-1">
                      <ScoreBar score={m.score} category={m.category} />
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-3 space-y-1 text-sm">
                {m.explanation.failed.map((s) => (
                  <p key={s} className="flex gap-1.5 text-red-700">
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {s}
                  </p>
                ))}
                {m.explanation.unmet.map((s) => (
                  <p key={s} className="flex gap-1.5 text-amber-700">
                    <X className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {s}
                  </p>
                ))}
                {m.explanation.met.map((s) => (
                  <p key={s} className="flex gap-1.5 text-emerald-700">
                    <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {s}
                  </p>
                ))}
              </div>
              {m.rejection_reason && <p className="mt-2 text-xs text-red-600">Motif du rejet : {m.rejection_reason}</p>}
              {m.customer_feedback && <p className="mt-1 text-xs text-slate-600">Retour client : {m.customer_feedback}</p>}
              {manage && m.id && m.is_active && (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
                  {m.status !== "proposed" && m.status !== "interested" && m.status !== "visit_scheduled" && (
                    <Button size="sm" icon={<Send className="h-3.5 w-3.5" />} onClick={() => act.mutate({ id: m.id!, status: "proposed" })}>
                      Proposer
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" icon={<ThumbsUp className="h-3.5 w-3.5" />} onClick={() => act.mutate({ id: m.id!, status: "interested" })}>
                    Intéressé
                  </Button>
                  {can("visits.manage") && (
                    <Button size="sm" variant="secondary" icon={<CalendarPlus className="h-3.5 w-3.5" />} onClick={() => setVisitFor(m)}>
                      Visite
                    </Button>
                  )}
                  {can("deals.manage") && (
                    <Button size="sm" variant="secondary" icon={<Handshake className="h-3.5 w-3.5" />} loading={deal.isPending} onClick={() => deal.mutate(m)}>
                      Transaction
                    </Button>
                  )}
                  {m.status !== "rejected" && (
                    <Button size="sm" variant="ghost" icon={<XCircle className="h-3.5 w-3.5" />} onClick={() => setRejecting(m)}>
                      Rejeter
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" icon={<BellRing className="h-3.5 w-3.5" />} onClick={() => renotify.mutate(m.id!)} title="Renvoyer la notification à l'agent">
                    Notifier
                  </Button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      <ReasonModal
        open={!!rejecting}
        onClose={() => setRejecting(null)}
        title="Rejeter ce bien"
        label="Motif du rejet (ex. trop cher, quartier, luminosité…)"
        onSubmit={(reason) => act.mutateAsync({ id: rejecting!.id!, status: "rejected", rejection_reason: reason })}
      />
      {visitFor && <VisitModal open onClose={() => setVisitFor(null)} req={req} propertyId={visitFor.property_id} matchId={visitFor.id} />}
    </>
  );
}

// ---------------------------------------------------------------- activities (shared with customers & deals)

export function ActivitiesPanel({ scope, id, canAdd }: { scope: "request" | "customer" | "deal"; id: string; canAdd: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const path = scope === "request" ? `/requests/${id}/activities` : scope === "customer" ? `/customers/${id}/activities` : `/deals/${id}/activities`;
  const q = useQuery({ queryKey: ["activities", scope, id], queryFn: () => api<Activity[]>(path) });
  const [type, setType] = useState("call");
  const [summary, setSummary] = useState("");
  const add = useMutation({
    mutationFn: () => api(path, { body: { type, summary } }),
    onSuccess: () => {
      setSummary("");
      qc.invalidateQueries({ queryKey: ["activities", scope, id] });
      qc.invalidateQueries({ queryKey: ["request", id] });
      toast.success("Interaction enregistrée.");
    },
    onError: toast.error,
  });
  const manual = Object.fromEntries(Object.entries(L.activityType).filter(([k]) => !["status_change", "web_contact", "offer"].includes(k)));
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {canAdd && scope !== "deal" && (
        <Card title="Nouvelle interaction">
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (summary.trim()) add.mutate();
            }}
          >
            <Field label="Type">{(fid) => <Select id={fid} value={type} onChange={(e) => setType(e.target.value)} options={options(manual)} />}</Field>
            <Field label="Compte rendu" required>{(fid) => <Textarea id={fid} rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} />}</Field>
            <Button type="submit" loading={add.isPending} disabled={!summary.trim()}>
              Ajouter
            </Button>
            <p className="text-xs text-slate-500">Un appel, e-mail ou rendez-vous enregistré passe automatiquement une nouvelle demande au statut « Contacté ».</p>
          </form>
        </Card>
      )}
      <Card title="Historique" className={canAdd && scope !== "deal" ? "lg:col-span-2" : "lg:col-span-3"}>
        {q.isLoading ? (
          <Spinner />
        ) : !q.data?.length ? (
          <EmptyState title="Aucune interaction" />
        ) : (
          <ol className="relative space-y-4 border-l border-slate-200 pl-4">
            {q.data.map((a) => (
              <li key={a.id} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand-500 ring-4 ring-white" />
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <Badge color={a.type === "status_change" ? "gray" : "teal"}>{L.activityType[a.type]}</Badge>
                  {dateTime(a.occurred_at)}
                  {a.created_by && <span>· {a.created_by.full_name}</span>}
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{a.summary}</p>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- tasks

export function TasksPanel({ requestId, customerId }: { requestId?: string; customerId?: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ["tasks", requestId ?? customerId];
  const q = useQuery({ queryKey: key, queryFn: () => api<Task[]>("/tasks", { query: { request_id: requestId, customer_id: customerId, status: "open,done" } }) });
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const add = useMutation({
    mutationFn: () => api("/tasks", { body: { title, due_at: fromLocalInput(due), request_id: requestId, customer_id: customerId } }),
    onSuccess: () => {
      setTitle("");
      setDue("");
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: toast.error,
  });
  const toggle = useMutation({
    mutationFn: (t: Task) => api(`/tasks/${t.id}`, { method: "PATCH", body: { status: t.status === "done" ? "open" : "done" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: toast.error,
  });
  return (
    <Card title="Tâches et rappels">
      <form
        className="mb-4 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim() && due) add.mutate();
        }}
      >
        <Input placeholder="Ex. Rappeler le client pour confirmer la visite" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Titre de la tâche" />
        <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className="sm:max-w-[220px]" aria-label="Échéance" />
        <Button type="submit" loading={add.isPending} disabled={!title.trim() || !due}>
          Ajouter
        </Button>
      </form>
      {!q.data?.length ? (
        <EmptyState title="Aucune tâche" />
      ) : (
        <ul className="divide-y divide-slate-100">
          {q.data.map((t) => (
            <li key={t.id} className="flex items-center gap-3 py-2">
              <button
                onClick={() => toggle.mutate(t)}
                className={`flex h-5 w-5 items-center justify-center rounded border ${t.status === "done" ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300"}`}
                aria-label={t.status === "done" ? "Rouvrir la tâche" : "Marquer comme terminée"}
              >
                {t.status === "done" && <CheckCircle2 className="h-4 w-4" />}
              </button>
              <div className="min-w-0 flex-1">
                <p className={`text-sm ${t.status === "done" ? "text-slate-400 line-through" : "text-slate-800"}`}>{t.title}</p>
                <p className={`text-xs ${t.status === "open" && new Date(t.due_at) < new Date() ? "font-medium text-red-600" : "text-slate-500"}`}>
                  {dateTime(t.due_at)} · {t.assigned_to.full_name}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- visits

function VisitsPanel({ req }: { req: CustomerRequest }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["visits", "request", req.id], queryFn: () => api<Page<Visit>>("/visits", { query: { request_id: req.id, order: "desc" } }) });
  return (
    <Card title="Visites" actions={can("visits.manage") && <Button size="sm" icon={<CalendarPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>Planifier une visite</Button>}>
      {!q.data?.items.length ? (
        <EmptyState title="Aucune visite" />
      ) : (
        <ul className="divide-y divide-slate-100">
          {q.data.items.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span>
                <strong>{dateTime(v.scheduled_at)}</strong> · <Link className="text-brand-700 hover:underline" to={`/app/properties/${v.property_id}`}>{v.property_reference}</Link> — {v.property_title}
              </span>
              <VisitStatusBadge s={v.status} />
            </li>
          ))}
        </ul>
      )}
      {open && <VisitModal open onClose={() => setOpen(false)} req={req} />}
    </Card>
  );
}

export function VisitModal({ open, onClose, req, propertyId, matchId }: { open: boolean; onClose: () => void; req: CustomerRequest; propertyId?: string; matchId?: string | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useAuth();
  const agents = useDirectory(true);
  const matches = useQuery({ queryKey: ["request-matches", req.id, false, false], queryFn: () => api<Match[]>(`/requests/${req.id}/matches`), enabled: !propertyId });
  const [pid, setPid] = useState(propertyId ?? "");
  const [when, setWhen] = useState("");
  const [duration, setDuration] = useState("45");
  const [agent, setAgent] = useState(req.assigned_agent?.id ?? "");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api("/visits", {
        body: { property_id: pid, request_id: req.id, match_id: matchId ?? null, scheduled_at: fromLocalInput(when), duration_minutes: Number(duration), agent_id: agent || null, notes: notes || null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visits"] });
      qc.invalidateQueries({ queryKey: ["request", req.id] });
      qc.invalidateQueries({ queryKey: ["request-matches", req.id] });
      toast.success("Visite planifiée.");
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Planifier une visite"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button loading={save.isPending} disabled={!pid || !when} onClick={() => save.mutate()}>
            Planifier
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {!propertyId && (
          <Field label="Bien" required>
            {(id) => (
              <Select id={id} value={pid} onChange={(e) => setPid(e.target.value)} placeholder="Choisir parmi les biens correspondants" options={(matches.data ?? []).map((m) => ({ value: m.property_id, label: `${m.property_reference} — ${m.property_title}` }))} />
            )}
          </Field>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Date et heure" required>{(id) => <Input id={id} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}</Field>
          <Field label="Durée (minutes)">{(id) => <Input id={id} type="number" min={10} max={600} value={duration} onChange={(e) => setDuration(e.target.value)} />}</Field>
        </div>
        {can("requests.assign") && (
          <Field label="Agent">{(id) => <Select id={id} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="Agent de la demande" options={(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))} />}</Field>
        )}
        <Field label="Notes">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- status & assignment modals

function StatusModal({ open, onClose, req, onDone, canArchive }: { open: boolean; onClose: () => void; req: CustomerRequest; onDone: () => void; canArchive: boolean }) {
  const toast = useToast();
  const [status, setStatus] = useState(req.status);
  const [reason, setReason] = useState("");
  const [follow, setFollow] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api(`/requests/${req.id}`, {
        method: "PATCH",
        body: { status, ...(reason ? { close_reason: reason } : {}), ...(follow ? { next_follow_up_at: fromLocalInput(follow) } : {}) },
      }),
    onSuccess: () => {
      onDone();
      toast.success("Statut mis à jour.");
      onClose();
    },
    onError: toast.error,
  });
  const statuses = Object.fromEntries(Object.entries(L.requestStatus).filter(([k]) => canArchive || k !== "archived"));
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Changer le statut"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button loading={save.isPending} disabled={status === "closed_lost" && reason.trim().length < 2} onClick={() => save.mutate()}>
            Enregistrer
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Statut">{(id) => <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)} options={options(statuses)} />}</Field>
        {(status === "closed_lost" || status === "archived") && (
          <Field label="Motif" required={status === "closed_lost"}>{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex. a trouvé par un autre canal, budget insuffisant…" />}</Field>
        )}
        {!["converted", "closed_lost", "archived"].includes(status) && (
          <Field label="Prochaine relance (optionnel)">{(id) => <Input id={id} type="datetime-local" value={follow} onChange={(e) => setFollow(e.target.value)} />}</Field>
        )}
      </div>
    </Modal>
  );
}

function AssignModal({ open, onClose, req, onDone, meId }: { open: boolean; onClose: () => void; req: CustomerRequest; onDone: () => void; meId?: string }) {
  const toast = useToast();
  const agents = useDirectory(true);
  const [agent, setAgent] = useState(req.assigned_agent?.id ?? "");
  const save = useMutation({
    mutationFn: () => api(`/requests/${req.id}/assign`, { body: { agent_id: agent || null } }),
    onSuccess: () => {
      onDone();
      toast.success(agent ? "Demande assignée — l'agent a été notifié." : "Assignation retirée.");
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Assigner la demande"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            Assigner
          </Button>
        </>
      }
    >
      <Field label="Agent commercial">
        {(id) => <Select id={id} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="— Non assignée —" options={(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name + (a.id === meId ? " (moi)" : "") }))} />}
      </Field>
    </Modal>
  );
}
