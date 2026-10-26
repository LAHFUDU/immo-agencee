import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { DataTable, FilterPanel, MatchBadge, ScoreBar, type Column } from "../components/domain";
import { Badge, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select } from "../components/ui";
import { api, type Page } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, relative } from "../lib/format";
import { useDirectory, useUrlFilters } from "../lib/hooks";
import { L, options } from "../lib/i18n";
import type { Match } from "../lib/types";

const DEFAULTS = {} as Record<string, string>;

export default function Matching() {
  const { can } = useAuth();
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const agents = useDirectory(true);
  const query = useMemo(() => ({ ...values, page: String(page), page_size: "30" }), [values, page]);
  const q = useQuery({ queryKey: ["matches", query], queryFn: () => api<Page<Match>>("/matches", { query }), placeholderData: (p) => p });
  const activeCount = Object.entries(values).filter(([k, v]) => v && k !== "page").length;
  const columns: Column<Match>[] = [
    {
      key: "req",
      header: "Client",
      render: (m) => (
        <div>
          <Link to={`/app/requests/${m.request_id}`} className="font-medium text-brand-800 hover:underline">
            {m.customer_name}
          </Link>
          <p className="text-xs text-slate-500">{m.request_reference}</p>
        </div>
      ),
    },
    {
      key: "prop",
      header: "Bien",
      render: (m) => (
        <div>
          <Link to={`/app/properties/${m.property_id}`} className="text-slate-800 hover:underline">
            {m.property_reference} — {m.property_title}
          </Link>
          <p className="text-xs text-slate-500">
            {m.property_city}
            {m.property_neighborhood ? ` / ${m.property_neighborhood}` : ""} · {money(m.property_price, m.property_currency)}
          </p>
        </div>
      ),
    },
    { key: "cat", header: "Catégorie", render: (m) => <MatchBadge category={m.category} /> },
    { key: "score", header: "Score", render: (m) => <ScoreBar score={m.score} category={m.category} /> },
    { key: "status", header: "Suivi", render: (m) => (m.status ? <Badge color={m.status === "rejected" ? "red" : m.status === "suggested" ? "gray" : "violet"}>{L.matchStatus[m.status]}</Badge> : null), secondary: true },
    { key: "agent", header: "Agent", render: (m) => m.agent?.full_name ?? <span className="text-amber-700">Non assignée</span>, secondary: true },
    { key: "when", header: "Calculée", render: (m) => <span className="text-slate-500">{relative(m.computed_at)}</span>, secondary: true },
  ];
  return (
    <>
      <PageHeader title="Correspondances" subtitle="Biens disponibles correspondant aux demandes ouvertes, classés par le moteur de correspondance (score 0–100)." />
      <FilterPanel page="matching" values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Catégorie">{(id) => <Select id={id} value={values.category ?? ""} onChange={(e) => set({ category: e.target.value })} placeholder="Toutes" options={options(L.matchCategory).filter((o) => o.value !== "ineligible")} />}</Field>
        <Field label="Score minimum">{(id) => <Input id={id} type="number" min={0} max={100} value={values.min_score ?? ""} onChange={(e) => set({ min_score: e.target.value })} />}</Field>
        <Field label="Suivi">{(id) => <Select id={id} value={values.status ?? ""} onChange={(e) => set({ status: e.target.value })} placeholder="Tous" options={options(L.matchStatus)} />}</Field>
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
        <Field label="Ville">{(id) => <Input id={id} value={values.city ?? ""} onChange={(e) => set({ city: e.target.value })} />}</Field>
      </FilterPanel>
      <Card>
        {q.error ? (
          <ErrorState error={q.error} />
        ) : (
          <>
            <DataTable rows={q.data?.items} columns={columns} loading={q.isFetching} rowHref={(m) => `/app/requests/${m.request_id}`} empty={<EmptyState title="Aucune correspondance active" />} />
            {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
          </>
        )}
      </Card>
    </>
  );
}
