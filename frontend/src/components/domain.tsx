import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bookmark, Download, Filter, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCatalog } from "../lib/hooks";
import { L } from "../lib/i18n";
import { Badge, Button, EmptyState, Input, Modal, Spinner, useToast, type BadgeColor } from "./ui";

// ---------------------------------------------------------------- badges

const REQUEST_COLORS: Record<string, BadgeColor> = {
  new: "blue", to_contact: "amber", contacted: "teal", proposed: "violet", visit_scheduled: "violet",
  negotiation: "amber", converted: "green", closed_lost: "red", archived: "gray",
};
const PROPERTY_COLORS: Record<string, BadgeColor> = {
  available: "green", reserved: "amber", under_negotiation: "violet", sold: "blue", rented: "blue", unavailable: "gray", archived: "gray",
};
const PRIORITY_COLORS: Record<string, BadgeColor> = { low: "gray", normal: "teal", high: "amber", urgent: "red" };
const MATCH_COLORS: Record<string, BadgeColor> = { exact: "green", strong: "teal", partial: "amber", ineligible: "red" };
const DEAL_COLORS: Record<string, BadgeColor> = { negotiation: "amber", reserved: "violet", won: "green", lost: "red", cancelled: "gray" };
const VISIT_COLORS: Record<string, BadgeColor> = { scheduled: "blue", done: "green", cancelled: "gray", no_show: "red" };

export const RequestStatusBadge = ({ s }: { s: string }) => <Badge color={REQUEST_COLORS[s]}>{L.requestStatus[s] ?? s}</Badge>;
export const PropertyStatusBadge = ({ s }: { s: string }) => <Badge color={PROPERTY_COLORS[s]}>{L.propertyStatus[s] ?? s}</Badge>;
export const PriorityBadge = ({ s }: { s: string }) => <Badge color={PRIORITY_COLORS[s]}>{L.priority[s] ?? s}</Badge>;
export const DealStatusBadge = ({ s }: { s: string }) => <Badge color={DEAL_COLORS[s]}>{L.dealStatus[s] ?? s}</Badge>;
export const VisitStatusBadge = ({ s }: { s: string }) => <Badge color={VISIT_COLORS[s]}>{L.visitStatus[s] ?? s}</Badge>;
export const MatchBadge = ({ category, score }: { category: string; score?: number | null }) => (
  <Badge color={MATCH_COLORS[category]}>
    {L.matchCategory[category] ?? category}
    {score !== undefined && score !== null && category !== "ineligible" ? ` · ${score}` : ""}
  </Badge>
);

export function ScoreBar({ score, category }: { score: number; category: string }) {
  const color = { exact: "bg-emerald-500", strong: "bg-brand-500", partial: "bg-amber-500", ineligible: "bg-red-400" }[category] ?? "bg-slate-400";
  return (
    <div className="flex items-center gap-2" aria-label={`Score ${score} sur 100`}>
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-semibold text-slate-700">{score}</span>
    </div>
  );
}

// ---------------------------------------------------------------- data table

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  /** hide on small screens */
  secondary?: boolean;
}

export function DataTable<T extends { id?: string | null }>({
  rows,
  columns,
  rowHref,
  loading,
  empty,
  rowKey,
  selectable,
  selected,
  onSelect,
}: {
  rows: T[] | undefined;
  columns: Column<T>[];
  rowHref?: (row: T) => string;
  loading?: boolean;
  empty?: ReactNode;
  rowKey?: (row: T, i: number) => string;
  selectable?: boolean;
  selected?: Set<string>;
  onSelect?: (ids: Set<string>) => void;
}) {
  const navigate = useNavigate();
  if (loading && !rows) return <Spinner />;
  if (!rows || rows.length === 0) return <>{empty ?? <EmptyState title="Aucun résultat" />}</>;
  const allIds = rows.map((r) => String(r.id));
  const allSelected = selectable && selected && allIds.every((id) => selected.has(id));
  return (
    <div className="scrollbar-thin -mx-4 overflow-x-auto sm:mx-0">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead>
          <tr>
            {selectable && (
              <th className="w-8 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label="Tout sélectionner"
                  checked={!!allSelected}
                  onChange={(e) => onSelect?.(e.target.checked ? new Set(allIds) : new Set())}
                />
              </th>
            )}
            {columns.map((c) => (
              <th key={c.key} scope="col" className={clsx("whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500", c.secondary && "hidden md:table-cell", c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => {
            const href = rowHref?.(r);
            return (
              <tr
                key={rowKey ? rowKey(r, i) : String(r.id ?? i)}
                className={clsx(href && "cursor-pointer hover:bg-brand-50/50", loading && "opacity-60")}
                onClick={(e) => {
                  if (!href || (e.target as HTMLElement).closest("a,button,input,select")) return;
                  navigate(href);
                }}
              >
                {selectable && (
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label="Sélectionner"
                      checked={selected?.has(String(r.id)) ?? false}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) next.add(String(r.id));
                        else next.delete(String(r.id));
                        onSelect?.(next);
                      }}
                    />
                  </td>
                )}
                {columns.map((c) => (
                  <td key={c.key} className={clsx("px-3 py-2.5 align-top", c.secondary && "hidden md:table-cell", c.className)}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- filter panel with saved presets

export function FilterPanel({
  page,
  values,
  onApply,
  children,
  activeCount,
}: {
  page: string;
  values: Record<string, string>;
  onApply: (v: Record<string, string>) => void;
  children: ReactNode;
  activeCount: number;
}) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const presets = useQuery({
    queryKey: ["saved-filters", page],
    queryFn: () => api<{ id: string; name: string; filters: Record<string, string> }[]>("/saved-filters", { query: { page } }),
  });
  const [name, setName] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const filters = Object.fromEntries(Object.entries(values).filter(([k, v]) => v && k !== "page"));
      return api("/saved-filters", { body: { page, name, filters } });
    },
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["saved-filters", page] });
      toast.success("Filtre enregistré.");
    },
    onError: toast.error,
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/saved-filters/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-filters", page] }),
  });

  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant={open ? "primary" : "secondary"} size="sm" icon={<Filter className="h-4 w-4" />} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Filtres{activeCount ? ` (${activeCount})` : ""}
        </Button>
        {activeCount > 0 && (
          <Button variant="ghost" size="sm" icon={<X className="h-4 w-4" />} onClick={() => onApply({})}>
            Réinitialiser
          </Button>
        )}
        {presets.data?.map((p) => (
          <span key={p.id} className="inline-flex items-center rounded-full border border-slate-200 bg-white text-xs shadow-sm">
            <button className="flex items-center gap-1 py-1 pl-2.5 pr-1 text-slate-700 hover:text-brand-800" onClick={() => onApply(p.filters)}>
              <Bookmark className="h-3 w-3" aria-hidden /> {p.name}
            </button>
            <button className="rounded-full p-1 text-slate-400 hover:text-red-600" aria-label={`Supprimer le filtre ${p.name}`} onClick={() => del.mutate(p.id)}>
              <Trash2 className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      {open && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <Input className="max-w-xs" placeholder="Nom du filtre à enregistrer" value={name} onChange={(e) => setName(e.target.value)} />
            <Button variant="secondary" size="sm" icon={<Bookmark className="h-4 w-4" />} disabled={!name.trim() || activeCount === 0} loading={save.isPending} onClick={() => save.mutate()}>
              Enregistrer ce filtre
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ExportButtons({ path, query, perm }: { path: string; query: Record<string, string>; perm: string }) {
  const { can } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  if (!can(perm)) return null;
  const run = async (fmt: "csv" | "xlsx") => {
    setBusy(fmt);
    try {
      const q = Object.fromEntries(Object.entries(query).filter(([k]) => k !== "page"));
      await download(path, { ...q, fmt });
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Button variant="secondary" size="sm" icon={<Download className="h-4 w-4" />} loading={busy === "csv"} onClick={() => run("csv")}>
        CSV
      </Button>
      <Button variant="secondary" size="sm" icon={<Download className="h-4 w-4" />} loading={busy === "xlsx"} onClick={() => run("xlsx")}>
        Excel
      </Button>
    </>
  );
}

// ---------------------------------------------------------------- feature picker

export function FeaturePicker({ value, onChange, label }: { value: string[]; onChange: (v: string[]) => void; label?: string }) {
  const { data } = useCatalog();
  return (
    <fieldset>
      {label && <legend className="mb-1 text-sm font-medium text-slate-700">{label}</legend>}
      <div className="flex flex-wrap gap-1.5">
        {data?.features
          .filter((f) => f.is_active || value.includes(f.code))
          .map((f) => {
            const on = value.includes(f.code);
            return (
              <button
                type="button"
                key={f.code}
                aria-pressed={on}
                onClick={() => onChange(on ? value.filter((x) => x !== f.code) : [...value, f.code])}
                className={clsx(
                  "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                  on ? "border-brand-600 bg-brand-700 text-white" : "border-slate-300 bg-white text-slate-600 hover:border-brand-400",
                )}
              >
                {f.label}
              </button>
            );
          })}
      </div>
    </fieldset>
  );
}

export function FeatureList({ codes }: { codes: string[] }) {
  const { featureLabel } = useCatalog();
  if (!codes.length) return <span className="text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {codes.map((c) => (
        <Badge key={c} color="teal">
          {featureLabel(c)}
        </Badge>
      ))}
    </div>
  );
}

export function useOptionsFromCatalog() {
  const { data } = useCatalog();
  return {
    types: (data?.property_types ?? []).filter((t) => t.is_active).map((t) => ({ value: t.code, label: t.label })),
    cities: (data?.cities ?? []).map((c) => ({ value: c, label: c })),
  };
}

export function ReasonModal({ open, onClose, title, label, onSubmit, confirmLabel = "Valider" }: { open: boolean; onClose: () => void; title: string; label: string; onSubmit: (reason: string) => Promise<unknown>; confirmLabel?: string }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button
            loading={busy}
            disabled={reason.trim().length < 2}
            onClick={async () => {
              setBusy(true);
              try {
                await onSubmit(reason.trim());
                setReason("");
                onClose();
              } catch (e) {
                toast.error(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="reason-input">
        {label}
      </label>
      <Input id="reason-input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} />
    </Modal>
  );
}
