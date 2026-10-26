import { useQuery } from "@tanstack/react-query";
import { AlarmClock, Hourglass, Plus } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { DataTable, ExportButtons, FilterPanel, MatchBadge, PriorityBadge, RequestStatusBadge, useOptionsFromCatalog, type Column } from "../../components/domain";
import { Alert, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { relative, money, range } from "../../lib/format";
import { useCatalog, useDirectory, useUrlFilters } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { CustomerRequest } from "../../lib/types";

const DEFAULTS = {} as Record<string, string>;

export default function RequestList({ waitingList = false }: { waitingList?: boolean }) {
  const { can } = useAuth();
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const { typeLabel } = useCatalog();
  const { types } = useOptionsFromCatalog();
  const agents = useDirectory(true);
  const query = useMemo(() => ({ ...values, ...(waitingList ? { waiting: "true", status: values.status || "open" } : {}), page: String(page), page_size: "25" }), [values, waitingList, page]);
  const q = useQuery({ queryKey: ["requests", query], queryFn: () => api<Page<CustomerRequest>>("/requests", { query }), placeholderData: (p) => p });
  const stats = useQuery({ queryKey: ["waiting-stats"], queryFn: () => api<{ waiting: number; waiting_unassigned: number }>("/requests-waiting/stats"), enabled: waitingList });

  const activeCount = Object.entries(values).filter(([k, v]) => v && !["page", "sort", "order"].includes(k)).length;
  const columns: Column<CustomerRequest>[] = [
    {
      key: "ref",
      header: "Demande",
      render: (r) => (
        <div>
          <Link to={`/app/requests/${r.id}`} className="font-medium text-brand-800 hover:underline">
            {r.customer.full_name}
          </Link>
          <p className="text-xs text-slate-500">
            {r.reference} · {r.customer.phone ?? r.customer.email}
          </p>
        </div>
      ),
    },
    {
      key: "crit",
      header: "Recherche",
      render: (r) => (
        <div className="text-slate-700">
          <p>
            {typeLabel(r.property_type)} · {L.transactionWish[r.transaction_type]}
          </p>
          <p className="text-xs text-slate-500">
            {r.city}
            {r.neighborhood ? ` / ${r.neighborhood}` : ""} · {range(r.budget_min, r.budget_max, (v) => money(v, r.currency))}
          </p>
        </div>
      ),
    },
    {
      key: "match",
      header: "Correspondances",
      render: (r) =>
        r.matches.active_count ? (
          <div className="flex flex-col items-start gap-1">
            <MatchBadge category={r.matches.best_category!} score={r.matches.best_score} />
            <span className="text-xs text-slate-500">{r.matches.active_count} bien(s)</span>
          </div>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700">
            <Hourglass className="h-3 w-3" /> En attente
          </span>
        ),
    },
    { key: "status", header: "Statut", render: (r) => <RequestStatusBadge s={r.status} /> },
    { key: "prio", header: "Priorité", render: (r) => <PriorityBadge s={r.priority} />, secondary: true },
    { key: "agent", header: "Agent", render: (r) => r.assigned_agent?.full_name ?? <span className="text-amber-700">Non assignée</span>, secondary: true },
    {
      key: "follow",
      header: "Relance",
      secondary: true,
      render: (r) =>
        r.next_follow_up_at ? (
          <span className={new Date(r.next_follow_up_at) < new Date() && !["converted", "closed_lost", "archived"].includes(r.status) ? "inline-flex items-center gap-1 font-medium text-red-600" : "text-slate-600"}>
            {new Date(r.next_follow_up_at) < new Date() && <AlarmClock className="h-3 w-3" />}
            {relative(r.next_follow_up_at)}
          </span>
        ) : (
          "—"
        ),
    },
    { key: "created", header: "Créée", render: (r) => <span className="text-slate-500">{relative(r.created_at)}</span>, secondary: true },
  ];

  return (
    <>
      <PageHeader
        title={waitingList ? "Liste d'attente" : "Demandes clients"}
        subtitle={
          waitingList
            ? "Clients dont la recherche ne correspond à aucun bien disponible. Ils sont automatiquement re-comparés à chaque ajout ou modification de bien."
            : "Toutes les recherches de biens enregistrées."
        }
        actions={
          <>
            <ExportButtons path="/requests/export" query={query} perm="requests.export" />
            {can("requests.create") && (
              <Link to="/app/requests/new">
                <Button icon={<Plus className="h-4 w-4" />}>Nouvelle demande</Button>
              </Link>
            )}
          </>
        }
      />
      {waitingList && stats.data && (
        <div className="mb-4">
          <Alert color={stats.data.waiting ? "amber" : "green"}>
            {stats.data.waiting
              ? `${stats.data.waiting} client(s) attendent un bien correspondant${stats.data.waiting_unassigned ? `, dont ${stats.data.waiting_unassigned} sans agent assigné` : ""}. L'agent assigné sera notifié dès qu'un bien correspondant sera disponible.`
              : "Tous les clients ont au moins un bien correspondant."}
          </Alert>
        </div>
      )}
      <FilterPanel page={waitingList ? "waiting" : "requests"} values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Client / téléphone / réf.">{(id) => <Input id={id} value={values.q ?? ""} onChange={(e) => set({ q: e.target.value })} />}</Field>
        {!waitingList && (
          <Field label="Statut">
            {(id) => <Select id={id} value={values.status ?? ""} onChange={(e) => set({ status: e.target.value })} placeholder="Tous (hors archivées)" options={[{ value: "open", label: "Ouvertes" }, ...options(L.requestStatus)]} />}
          </Field>
        )}
        <Field label="Priorité">{(id) => <Select id={id} value={values.priority ?? ""} onChange={(e) => set({ priority: e.target.value })} placeholder="Toutes" options={options(L.priority)} />}</Field>
        <Field label="Agent">
          {(id) => (
            <Select
              id={id}
              value={values.assigned_agent_id ?? ""}
              onChange={(e) => set({ assigned_agent_id: e.target.value })}
              placeholder="Tous"
              options={[{ value: "me", label: "Moi" }, { value: "none", label: "Non assignées" }, ...(can("requests.view_all") ? (agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name })) : [])]}
            />
          )}
        </Field>
        <Field label="Type de bien">{(id) => <Select id={id} value={values.property_type ?? ""} onChange={(e) => set({ property_type: e.target.value })} placeholder="Tous" options={types} />}</Field>
        <Field label="Achat / location">{(id) => <Select id={id} value={values.transaction_type ?? ""} onChange={(e) => set({ transaction_type: e.target.value })} placeholder="Tous" options={options(L.transactionWish)} />}</Field>
        <Field label="Ville">{(id) => <Input id={id} value={values.city ?? ""} onChange={(e) => set({ city: e.target.value })} />}</Field>
        <Field label="Quartier">{(id) => <Input id={id} value={values.neighborhood ?? ""} onChange={(e) => set({ neighborhood: e.target.value })} />}</Field>
        <Field label="Budget max. ≥">{(id) => <Input id={id} type="number" min={0} value={values.budget_min ?? ""} onChange={(e) => set({ budget_min: e.target.value })} />}</Field>
        <Field label="Budget max. ≤">{(id) => <Input id={id} type="number" min={0} value={values.budget_max ?? ""} onChange={(e) => set({ budget_max: e.target.value })} />}</Field>
        <Field label="Créée du">{(id) => <Input id={id} type="date" value={values.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} />}</Field>
        <Field label="au">{(id) => <Input id={id} type="date" value={values.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} />}</Field>
        {!waitingList && (
          <>
            <Field label="Correspondances">
              {(id) => <Select id={id} value={values.waiting ?? ""} onChange={(e) => set({ waiting: e.target.value })} placeholder="Toutes" options={[{ value: "false", label: "Avec biens correspondants" }, { value: "true", label: "En attente (aucun bien)" }]} />}
            </Field>
            <Field label="Score minimum">{(id) => <Input id={id} type="number" min={0} max={100} value={values.min_score ?? ""} onChange={(e) => set({ min_score: e.target.value })} />}</Field>
          </>
        )}
        <Field label="Relances">{(id) => <Select id={id} value={values.overdue ?? ""} onChange={(e) => set({ overdue: e.target.value })} placeholder="Toutes" options={[{ value: "true", label: "En retard uniquement" }]} />}</Field>
        <Field label="Tri">
          {(id) => (
            <Select
              id={id}
              value={`${values.sort ?? "created_at"}:${values.order ?? "desc"}`}
              onChange={(e) => {
                const [sort, order] = e.target.value.split(":");
                set({ sort, order });
              }}
              options={[
                { value: "created_at:desc", label: "Plus récentes" },
                { value: "created_at:asc", label: "Plus anciennes" },
                { value: "priority:desc", label: "Priorité" },
                { value: "next_follow_up_at:asc", label: "Prochaine relance" },
                { value: "budget_max:desc", label: "Budget décroissant" },
              ]}
            />
          )}
        </Field>
      </FilterPanel>
      <Card>
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <>
            <DataTable
              rows={q.data?.items}
              columns={columns}
              loading={q.isFetching}
              rowHref={(r) => `/app/requests/${r.id}`}
              empty={<EmptyState title={waitingList ? "Aucun client en attente" : "Aucune demande"}>{activeCount ? "Modifiez ou réinitialisez les filtres." : null}</EmptyState>}
            />
            {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
          </>
        )}
      </Card>
    </>
  );
}
