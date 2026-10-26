import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Globe, Plus, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { DataTable, ExportButtons, FilterPanel, PropertyStatusBadge, useOptionsFromCatalog, type Column } from "../../components/domain";
import { Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select, useToast } from "../../components/ui";
import { api, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money, num, relative } from "../../lib/format";
import { useCatalog, useDirectory, useUrlFilters } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Property } from "../../lib/types";

const DEFAULTS = {} as Record<string, string>;

export default function PropertyList() {
  const { can } = useAuth();
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const { typeLabel, data: catalog } = useCatalog();
  const { types } = useOptionsFromCatalog();
  const staff = useDirectory();
  const qc = useQueryClient();
  const toast = useToast();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState("");
  const query = useMemo(() => ({ ...values, page: String(page), page_size: "25" }), [values, page]);
  const q = useQuery({ queryKey: ["properties", query], queryFn: () => api<Page<Property>>("/properties", { query }), placeholderData: (p) => p });
  const bulk = useMutation({
    mutationFn: () => api<{ updated: number }>("/properties/bulk-status", { body: { ids: [...selected], status: bulkStatus } }),
    onSuccess: (r) => {
      toast.success(`${r.updated} bien(s) mis à jour.`);
      setSelected(new Set());
      setBulkStatus("");
      qc.invalidateQueries({ queryKey: ["properties"] });
    },
    onError: toast.error,
  });
  const activeCount = Object.entries(values).filter(([k, v]) => v && !["page", "sort", "order"].includes(k)).length;

  const columns: Column<Property>[] = [
    {
      key: "title",
      header: "Bien",
      render: (p) => (
        <div className="flex items-center gap-3">
          {p.photos[0] ? (
            <img src={p.photos[0].url} alt="" className="hidden h-11 w-14 rounded-md object-cover sm:block" loading="lazy" />
          ) : (
            <div className="hidden h-11 w-14 items-center justify-center rounded-md bg-slate-100 text-slate-300 sm:flex">
              <Building2 className="h-5 w-5" />
            </div>
          )}
          <div className="min-w-0">
            <Link to={`/app/properties/${p.id}`} className="block max-w-xs truncate font-medium text-brand-800 hover:underline">
              {p.title}
            </Link>
            <p className="text-xs text-slate-500">
              {p.reference} · {typeLabel(p.property_type)} · {L.transaction[p.transaction_type]}
              {p.is_published && <Globe className="ml-1 inline h-3 w-3 text-brand-600" aria-label="Publié" />}
            </p>
          </div>
        </div>
      ),
    },
    { key: "loc", header: "Localisation", render: (p) => <span>{p.city}{p.neighborhood ? <span className="text-slate-500"> / {p.neighborhood}</span> : null}</span> },
    { key: "price", header: "Prix", render: (p) => <span className="whitespace-nowrap font-medium">{money(p.price, p.currency)}</span> },
    { key: "surface", header: "Surface", render: (p) => num(p.surface, " m²"), secondary: true },
    { key: "rooms", header: "Ch.", render: (p) => p.bedrooms ?? "—", secondary: true },
    { key: "status", header: "Statut", render: (p) => <PropertyStatusBadge s={p.status} /> },
    { key: "matches", header: "Demandes", render: (p) => (p.active_match_count ? <span className="font-medium text-emerald-700">{p.active_match_count}</span> : <span className="text-slate-400">0</span>), secondary: true },
    { key: "upd", header: "Mis à jour", render: (p) => <span className="text-slate-500">{relative(p.updated_at)}</span>, secondary: true },
  ];

  return (
    <>
      <PageHeader
        title="Inventaire des biens"
        subtitle="Appartements, maisons, villas, locaux et terrains."
        actions={
          <>
            <ExportButtons path="/properties/export" query={query} perm="properties.export" />
            {can("properties.import") && (
              <Link to="/app/properties/import">
                <Button variant="secondary" icon={<Upload className="h-4 w-4" />}>
                  Importer
                </Button>
              </Link>
            )}
            {can("properties.create") && (
              <Link to="/app/properties/new">
                <Button icon={<Plus className="h-4 w-4" />}>Nouveau bien</Button>
              </Link>
            )}
          </>
        }
      />
      <FilterPanel page="properties" values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Recherche">{(id) => <Input id={id} value={values.q ?? ""} onChange={(e) => set({ q: e.target.value })} placeholder="Titre, réf., quartier…" />}</Field>
        <Field label="Référence">{(id) => <Input id={id} value={values.reference ?? ""} onChange={(e) => set({ reference: e.target.value })} />}</Field>
        <Field label="Type">{(id) => <Select id={id} value={values.property_type ?? ""} onChange={(e) => set({ property_type: e.target.value })} placeholder="Tous" options={types} />}</Field>
        <Field label="Vente / location">{(id) => <Select id={id} value={values.transaction_type ?? ""} onChange={(e) => set({ transaction_type: e.target.value })} placeholder="Toutes" options={options(L.transaction)} />}</Field>
        <Field label="Statut">
          {(id) => (
            <Select
              id={id}
              value={values.status ?? ""}
              onChange={(e) => set({ status: e.target.value })}
              placeholder="Tous (hors archivés)"
              options={[...options(L.propertyStatus), { value: "sold,rented", label: "Vendus ou loués" }, { value: "under_negotiation,reserved", label: "Négociation ou réservés" }]}
            />
          )}
        </Field>
        <Field label="Ville">
          {(id) => (
            <>
              <Input id={id} list="prop-cities" value={values.city ?? ""} onChange={(e) => set({ city: e.target.value })} />
              <datalist id="prop-cities">{catalog?.cities.map((c) => <option key={c} value={c} />)}</datalist>
            </>
          )}
        </Field>
        <Field label="Quartier">{(id) => <Input id={id} value={values.neighborhood ?? ""} onChange={(e) => set({ neighborhood: e.target.value })} />}</Field>
        <Field label="Chambres min.">{(id) => <Input id={id} type="number" min={0} value={values.bedrooms_min ?? ""} onChange={(e) => set({ bedrooms_min: e.target.value })} />}</Field>
        <Field label="Prix min.">{(id) => <Input id={id} type="number" min={0} value={values.price_min ?? ""} onChange={(e) => set({ price_min: e.target.value })} />}</Field>
        <Field label="Prix max.">{(id) => <Input id={id} type="number" min={0} value={values.price_max ?? ""} onChange={(e) => set({ price_max: e.target.value })} />}</Field>
        <Field label="Surface min. (m²)">{(id) => <Input id={id} type="number" min={0} value={values.surface_min ?? ""} onChange={(e) => set({ surface_min: e.target.value })} />}</Field>
        <Field label="Surface max. (m²)">{(id) => <Input id={id} type="number" min={0} value={values.surface_max ?? ""} onChange={(e) => set({ surface_max: e.target.value })} />}</Field>
        <Field label="Responsable">{(id) => <Select id={id} value={values.responsible_id ?? ""} onChange={(e) => set({ responsible_id: e.target.value })} placeholder="Tous" options={(staff.data ?? []).map((u) => ({ value: u.id, label: u.full_name }))} />}</Field>
        <Field label="Publication">{(id) => <Select id={id} value={values.is_published ?? ""} onChange={(e) => set({ is_published: e.target.value })} placeholder="Tous" options={[{ value: "true", label: "Publiés sur le site" }, { value: "false", label: "Non publiés" }]} />}</Field>
        <Field label="Ajouté du">{(id) => <Input id={id} type="date" value={values.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} />}</Field>
        <Field label="au">{(id) => <Input id={id} type="date" value={values.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} />}</Field>
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
                { value: "created_at:desc", label: "Plus récents" },
                { value: "updated_at:desc", label: "Dernière mise à jour" },
                { value: "price:asc", label: "Prix croissant" },
                { value: "price:desc", label: "Prix décroissant" },
                { value: "surface:desc", label: "Surface décroissante" },
                { value: "reference:asc", label: "Référence" },
              ]}
            />
          )}
        </Field>
      </FilterPanel>
      {selected.size > 0 && can("properties.edit") && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
          <span className="font-medium">{selected.size} sélectionné(s)</span>
          <Select
            className="max-w-[220px]"
            aria-label="Nouveau statut"
            value={bulkStatus}
            onChange={(e) => setBulkStatus(e.target.value)}
            placeholder="Changer le statut…"
            options={options(L.propertyStatus).filter((o) => o.value !== "archived" || can("properties.archive"))}
          />
          <Button size="sm" disabled={!bulkStatus} loading={bulk.isPending} onClick={() => bulk.mutate()}>
            Appliquer
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Désélectionner
          </Button>
        </div>
      )}
      <Card>
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <>
            <DataTable
              rows={q.data?.items}
              columns={columns}
              loading={q.isFetching}
              rowHref={(p) => `/app/properties/${p.id}`}
              selectable={can("properties.edit")}
              selected={selected}
              onSelect={setSelected}
              empty={<EmptyState title="Aucun bien" icon={<Building2 className="h-10 w-10" />}>{activeCount ? "Modifiez ou réinitialisez les filtres." : "Ajoutez votre premier bien ou importez un fichier."}</EmptyState>}
            />
            {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
          </>
        )}
      </Card>
    </>
  );
}
