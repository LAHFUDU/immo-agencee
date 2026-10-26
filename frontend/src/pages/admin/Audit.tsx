import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { FilterPanel } from "../../components/domain";
import { Badge, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { dateTime } from "../../lib/format";
import { useUrlFilters } from "../../lib/hooks";

interface Row {
  id: number;
  user: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_label: string | null;
  changes: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

const ENTITIES: Record<string, string> = {
  auth: "Authentification", user: "Utilisateur", role: "Rôle", property: "Bien", request: "Demande", customer: "Client", deal: "Transaction",
  visit: "Visite", owner: "Propriétaire", setting: "Paramètre", commission_rule: "Règle de commission", report: "Rapport", property_type: "Type de bien", feature: "Équipement",
};
const DEFAULTS = {} as Record<string, string>;

export default function AuditPage() {
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const [open, setOpen] = useState<number | null>(null);
  const query = useMemo(() => ({ ...values, page: String(page), page_size: "50" }), [values, page]);
  const q = useQuery({ queryKey: ["audit", query], queryFn: () => api<{ items: Row[]; total: number; page: number; page_size: number }>("/audit-logs", { query }), placeholderData: (p) => p });
  const activeCount = Object.entries(values).filter(([k, v]) => v && k !== "page").length;
  return (
    <>
      <PageHeader title="Journal d'audit" subtitle="Actions sensibles : connexions, créations, modifications, exports, changements de droits." />
      <FilterPanel page="audit" values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Objet">{(id) => <Select id={id} value={values.entity_type ?? ""} onChange={(e) => set({ entity_type: e.target.value })} placeholder="Tous" options={Object.entries(ENTITIES).map(([value, label]) => ({ value, label }))} />}</Field>
        <Field label="Action (code)">{(id) => <Input id={id} value={values.action ?? ""} onChange={(e) => set({ action: e.target.value })} placeholder="ex. login_failed, export" />}</Field>
        <Field label="Libellé">{(id) => <Input id={id} value={values.q ?? ""} onChange={(e) => set({ q: e.target.value })} placeholder="référence, e-mail…" />}</Field>
        <Field label="Du">{(id) => <Input id={id} type="date" value={values.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} />}</Field>
        <Field label="Au">{(id) => <Input id={id} type="date" value={values.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} />}</Field>
      </FilterPanel>
      <Card>
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data?.items.length ? (
          <EmptyState title="Aucune entrée" />
        ) : (
          <ul className="divide-y divide-slate-100">
            {q.data.items.map((r) => (
              <li key={r.id} className="py-2 text-sm">
                <button className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                  <span className="w-36 shrink-0 text-xs text-slate-500">{dateTime(r.created_at)}</span>
                  <Badge color={r.action.includes("failed") ? "red" : r.action === "export" ? "amber" : "teal"}>{r.action}</Badge>
                  <span className="text-slate-500">{ENTITIES[r.entity_type] ?? r.entity_type}</span>
                  <span className="font-medium text-slate-800">{r.entity_label}</span>
                  <span className="ml-auto text-xs text-slate-500">{r.user ?? "Système / public"}{r.ip ? ` · ${r.ip}` : ""}</span>
                </button>
                {open === r.id && r.changes && <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{JSON.stringify(r.changes, null, 2)}</pre>}
              </li>
            ))}
          </ul>
        )}
        {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
      </Card>
    </>
  );
}
