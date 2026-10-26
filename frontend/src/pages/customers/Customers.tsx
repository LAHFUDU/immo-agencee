import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ClipboardList, Pencil, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DataTable, DealStatusBadge, ExportButtons, FilterPanel, MatchBadge, RequestStatusBadge, type Column } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Button, Card, ConfirmButton, EmptyState, ErrorState, Field, Input, KV, Modal, PageHeader, Pagination, Select, Spinner, Tabs, Textarea, useToast } from "../../components/ui";
import { api, ApiError, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, money, relative } from "../../lib/format";
import { useCatalog, useDirectory, useUrlFilters } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Customer, CustomerRequest, Deal, DuplicateCandidate } from "../../lib/types";
import { ActivitiesPanel, TasksPanel } from "../requests/RequestDetail";

const DEFAULTS = {} as Record<string, string>;

export function CustomerList() {
  const { can } = useAuth();
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const agents = useDirectory(true);
  const [creating, setCreating] = useState(false);
  const query = useMemo(() => ({ ...values, page: String(page), page_size: "25" }), [values, page]);
  const q = useQuery({ queryKey: ["customers", query], queryFn: () => api<Page<Customer>>("/customers", { query }), placeholderData: (p) => p });
  const activeCount = Object.entries(values).filter(([k, v]) => v && k !== "page").length;
  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Client",
      render: (c) => (
        <div>
          <Link to={`/app/customers/${c.id}`} className="font-medium text-brand-800 hover:underline">
            {c.full_name}
          </Link>
          <p className="text-xs text-slate-500">{c.reference}</p>
        </div>
      ),
    },
    { key: "contact", header: "Contact", render: (c) => <div className="text-sm">{c.phone ?? "—"}<p className="text-xs text-slate-500">{c.email}</p></div> },
    { key: "source", header: "Source", render: (c) => L.source[c.source], secondary: true },
    { key: "agent", header: "Agent", render: (c) => c.assigned_agent?.full_name ?? "—", secondary: true },
    { key: "created", header: "Créé", render: (c) => <span className="text-slate-500">{relative(c.created_at)}</span>, secondary: true },
  ];
  return (
    <>
      <PageHeader
        title="Clients"
        subtitle="Profils, historique des contacts et des demandes."
        actions={
          <>
            <ExportButtons path="/customers/export" query={query} perm="customers.export" />
            {can("customers.create") && (
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
                Nouveau client
              </Button>
            )}
          </>
        }
      />
      <FilterPanel page="customers" values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Nom / téléphone / e-mail / réf.">{(id) => <Input id={id} value={values.q ?? ""} onChange={(e) => set({ q: e.target.value })} />}</Field>
        <Field label="Source">{(id) => <Select id={id} value={values.source ?? ""} onChange={(e) => set({ source: e.target.value })} placeholder="Toutes" options={options(L.source)} />}</Field>
        <Field label="Agent">{(id) => <Select id={id} value={values.assigned_agent_id ?? ""} onChange={(e) => set({ assigned_agent_id: e.target.value })} placeholder="Tous" options={[{ value: "me", label: "Moi" }, ...(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))]} />}</Field>
        <Field label="Archivés">{(id) => <Select id={id} value={values.archived ?? ""} onChange={(e) => set({ archived: e.target.value })} placeholder="Clients actifs" options={[{ value: "true", label: "Clients archivés" }]} />}</Field>
      </FilterPanel>
      <Card>
        {q.error ? (
          <ErrorState error={q.error} />
        ) : (
          <>
            <DataTable rows={q.data?.items} columns={columns} loading={q.isFetching} rowHref={(c) => `/app/customers/${c.id}`} empty={<EmptyState title="Aucun client" />} />
            {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
          </>
        )}
      </Card>
      {creating && <CustomerModal onClose={() => setCreating(false)} />}
    </>
  );
}

function CustomerModal({ customer, onClose }: { customer?: Customer; onClose: () => void }) {
  const { can } = useAuth();
  const agents = useDirectory(true);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [f, setF] = useState({
    full_name: customer?.full_name ?? "", phone: customer?.phone ?? "", email: customer?.email ?? "",
    preferred_contact: customer?.preferred_contact ?? "phone", source: customer?.source ?? "phone",
    preferences: customer?.preferences ?? "", internal_notes: customer?.internal_notes ?? "", assigned_agent_id: customer?.assigned_agent?.id ?? "",
  });
  const [dups, setDups] = useState<DuplicateCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const body = () => {
    const b: Record<string, unknown> = {
      full_name: f.full_name.trim(), phone: f.phone.trim() || null, email: f.email.trim() || null, preferred_contact: f.preferred_contact,
      source: f.source, preferences: f.preferences || null, internal_notes: f.internal_notes || null,
    };
    if (can("requests.assign")) b.assigned_agent_id = f.assigned_agent_id || null;
    return b;
  };
  const save = useMutation({
    mutationFn: (allow: boolean) =>
      customer ? api<Customer>(`/customers/${customer.id}`, { method: "PATCH", body: body() }) : api<Customer>("/customers", { body: body(), query: { allow_duplicate: allow } }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      qc.invalidateQueries({ queryKey: ["customer", c.id] });
      toast.success(customer ? "Client mis à jour." : "Client créé.");
      onClose();
      if (!customer) navigate(`/app/customers/${c.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setDups((e.detail as { duplicates: DuplicateCandidate[] }).duplicates);
      else setError(e instanceof Error ? e.message : "Erreur");
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={customer ? "Modifier le client" : "Nouveau client"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          {dups && (
            <Button variant="secondary" onClick={() => save.mutate(true)}>
              Créer quand même
            </Button>
          )}
          <Button loading={save.isPending} disabled={f.full_name.trim().length < 2 || (!f.phone.trim() && !f.email.trim())} onClick={() => save.mutate(false)}>
            Enregistrer
          </Button>
        </>
      }
    >
      {error && <div className="mb-3"><Alert color="red">{error}</Alert></div>}
      {dups && (
        <div className="mb-3">
          <Alert color="amber" title="Doublon possible">
            {dups.map((d) => (
              <p key={d.id}>
                <Link className="underline" to={`/app/customers/${d.id}`} onClick={onClose}>
                  {d.full_name} ({d.reference})
                </Link>{" "}
                — {d.reason}
              </p>
            ))}
          </Alert>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nom complet" required>{(id) => <Input id={id} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />}</Field>
        <Field label="Téléphone">{(id) => <Input id={id} type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
        <Field label="E-mail">{(id) => <Input id={id} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
        <Field label="Contact préféré">{(id) => <Select id={id} value={f.preferred_contact} onChange={(e) => setF({ ...f, preferred_contact: e.target.value })} options={options(L.contactMethod)} />}</Field>
        <Field label="Source">{(id) => <Select id={id} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} options={options(L.source)} />}</Field>
        {can("requests.assign") && <Field label="Agent">{(id) => <Select id={id} value={f.assigned_agent_id} onChange={(e) => setF({ ...f, assigned_agent_id: e.target.value })} placeholder="—" options={(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))} />}</Field>}
      </div>
      <Field label="Préférences générales" className="mt-3">{(id) => <Textarea id={id} value={f.preferences} onChange={(e) => setF({ ...f, preferences: e.target.value })} />}</Field>
      <Field label="Notes internes" className="mt-3">{(id) => <Textarea id={id} value={f.internal_notes} onChange={(e) => setF({ ...f, internal_notes: e.target.value })} />}</Field>
    </Modal>
  );
}

export function CustomerDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const { typeLabel } = useCatalog();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<"requests" | "activities" | "tasks" | "deals">("requests");
  const [editing, setEditing] = useState(false);
  const q = useQuery({ queryKey: ["customer", id], queryFn: () => api<{ customer: Customer; requests: CustomerRequest[]; deals: Deal[] }>(`/customers/${id}`) });
  useEffect(() => setTab("requests"), [id]);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const { customer: c, requests, deals } = q.data!;
  return (
    <>
      <PageHeader
        back={<BackLink to="/app/customers">Clients</BackLink>}
        title={c.full_name}
        subtitle={`${c.reference} · client depuis le ${date(c.created_at)}${c.is_archived ? " · archivé" : ""}`}
        actions={
          <>
            {can("requests.create") && (
              <Link to={`/app/requests/new?customer_id=${c.id}`}>
                <Button variant="secondary" icon={<ClipboardList className="h-4 w-4" />}>
                  Nouvelle demande
                </Button>
              </Link>
            )}
            {can("customers.edit") && (
              <Button variant="secondary" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditing(true)}>
                Modifier
              </Button>
            )}
            {can("customers.archive") && (
              <ConfirmButton
                icon={<Archive className="h-4 w-4" />}
                title={c.is_archived ? "Réactiver le client" : "Archiver le client"}
                message={c.is_archived ? "Le client redeviendra visible dans les listes." : "Le client sera masqué des listes. Son historique est conservé."}
                onConfirm={async () => {
                  await api(`/customers/${c.id}/archive`, { method: "POST", query: { archived: !c.is_archived } });
                  qc.invalidateQueries({ queryKey: ["customer", id] });
                  toast.success("Client mis à jour.");
                }}
              >
                {c.is_archived ? "Réactiver" : "Archiver"}
              </ConfirmButton>
            )}
          </>
        }
      />
      <Card className="mb-4">
        <KV
          cols={3}
          items={[
            ["Téléphone", c.phone],
            ["E-mail", c.email],
            ["Contact préféré", L.contactMethod[c.preferred_contact]],
            ["Source", L.source[c.source]],
            ["Agent", c.assigned_agent?.full_name ?? "—"],
            ["Préférences", c.preferences],
            ["Notes internes", c.internal_notes],
          ]}
        />
      </Card>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "requests", label: `Demandes (${requests.length})` },
          { value: "activities", label: "Contacts & historique" },
          { value: "tasks", label: "Tâches" },
          ...(can("deals.view") ? [{ value: "deals" as const, label: `Transactions (${deals.length})` }] : []),
        ]}
      />
      {tab === "requests" && (
        <Card>
          {!requests.length ? (
            <EmptyState title="Aucune demande visible" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {requests.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                  <Link to={`/app/requests/${r.id}`} className="min-w-0 flex-1 text-brand-800 hover:underline">
                    {r.reference} — {typeLabel(r.property_type)} ({L.transactionWish[r.transaction_type]}) · {r.city}
                  </Link>
                  {r.matches.active_count ? <MatchBadge category={r.matches.best_category!} score={r.matches.best_score} /> : <span className="text-xs text-amber-700">En attente</span>}
                  <RequestStatusBadge s={r.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {tab === "activities" && <ActivitiesPanel scope="customer" id={c.id} canAdd={can("customers.edit")} />}
      {tab === "tasks" && <TasksPanel customerId={c.id} />}
      {tab === "deals" && (
        <Card>
          {!deals.length ? (
            <EmptyState title="Aucune transaction" />
          ) : (
            <ul className="divide-y divide-slate-100">
              {deals.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                  <Link to={`/app/deals/${d.id}`} className="min-w-0 flex-1 text-brand-800 hover:underline">
                    {d.reference} — {d.property_reference} {d.property_title}
                  </Link>
                  <span>{money(d.agreed_price ?? d.asking_price, d.currency)}</span>
                  <DealStatusBadge s={d.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {editing && <CustomerModal customer={c} onClose={() => setEditing(false)} />}
    </>
  );
}
