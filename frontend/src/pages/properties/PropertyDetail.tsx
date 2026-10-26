import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Download, FileText, Globe, ImagePlus, Lock, Pencil, Star, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FeatureList, MatchBadge, PropertyStatusBadge, ScoreBar } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Badge, Button, Card, Checkbox, ConfirmButton, EmptyState, ErrorState, Field, Input, KV, Modal, PageHeader, Select, Spinner, Tabs, useToast } from "../../components/ui";
import { api, download, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, dateTime, money, num } from "../../lib/format";
import { useCatalog } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Match, Property, Visit } from "../../lib/types";

interface Doc {
  id: string;
  filename: string;
  label: string | null;
  content_type: string;
  size: number;
  is_confidential: boolean;
  created_at: string;
}

const FIELD_LABELS: Record<string, string> = {
  status: "Statut", price: "Prix", title: "Titre", description: "Description", city: "Ville", neighborhood: "Quartier", surface: "Surface",
  bedrooms: "Chambres", bathrooms: "Salles de bain", features: "Équipements", is_published: "Publication", address: "Adresse",
  internal_notes: "Notes internes", owner_id: "Propriétaire", responsible_id: "Responsable", property_type: "Type", transaction_type: "Transaction",
  floor: "Étage", currency: "Devise", latitude: "Latitude", longitude: "Longitude", reason: "Motif", count: "Nombre", filename: "Fichier",
};
const ACTION_LABELS: Record<string, string> = {
  create: "Création", update: "Modification", status_change: "Changement de statut", photos_upload: "Photos ajoutées", photo_delete: "Photo supprimée",
  document_upload: "Document ajouté", document_delete: "Document supprimé", import: "Import",
};

export default function PropertyDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const { typeLabel } = useCatalog();
  const [tab, setTab] = useState<"info" | "photos" | "documents" | "matches" | "visits" | "history">("info");
  const [statusOpen, setStatusOpen] = useState(false);
  const q = useQuery({ queryKey: ["property", id], queryFn: () => api<Property>(`/properties/${id}`) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const p = q.data!;

  const tabs: { value: typeof tab; label: string }[] = [
    { value: "info", label: "Informations" },
    { value: "photos", label: `Photos (${p.photos.length})` },
  ];
  if (p.confidential_visible || can("properties.view")) tabs.push({ value: "documents", label: "Documents" });
  if (can("matches.view", "requests.view")) tabs.push({ value: "matches", label: `Demandes correspondantes (${p.active_match_count ?? 0})` });
  if (can("visits.view")) tabs.push({ value: "visits", label: "Visites" });
  tabs.push({ value: "history", label: "Historique" });

  return (
    <>
      <PageHeader
        back={<BackLink to="/app/properties">Biens</BackLink>}
        title={
          <span className="flex flex-wrap items-center gap-2">
            {p.title} <PropertyStatusBadge s={p.status} />
            {p.is_published && (
              <Badge color="teal">
                <Globe className="h-3 w-3" /> Publié
              </Badge>
            )}
          </span>
        }
        subtitle={`${p.reference} · ${typeLabel(p.property_type)} · ${L.transaction[p.transaction_type]} · ${p.city}${p.neighborhood ? " / " + p.neighborhood : ""}`}
        actions={
          can("properties.edit") && (
            <>
              <Button variant="secondary" onClick={() => setStatusOpen(true)}>
                Changer le statut
              </Button>
              <Link to={`/app/properties/${p.id}/edit`}>
                <Button variant="secondary" icon={<Pencil className="h-4 w-4" />}>
                  Modifier
                </Button>
              </Link>
            </>
          )
        }
      />
      {["sold", "rented", "unavailable", "archived"].includes(p.status) && (
        <div className="mb-4">
          <Alert color="blue">Ce bien n'est plus proposé comme correspondance aux clients (statut : {L.propertyStatus[p.status]}). Son historique est conservé.</Alert>
        </div>
      )}
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === "info" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Caractéristiques" className="lg:col-span-2">
            <div className="mb-4 flex items-baseline gap-3">
              <span className="text-2xl font-semibold text-brand-900">{money(p.price, p.currency)}</span>
              {p.transaction_type === "rent" && <span className="text-sm text-slate-500">/ mois</span>}
            </div>
            <KV
              items={[
                ["Surface", num(p.surface, " m²")],
                ["Chambres", p.bedrooms ?? "—"],
                ["Salles de bain", p.bathrooms ?? "—"],
                ["Étage", p.floor ?? "—"],
                ["Équipements", <FeatureList key="f" codes={p.features} />],
                ["Responsable", p.responsible?.full_name ?? "—"],
                ["Ajouté le", date(p.created_at)],
                ["Dernière mise à jour", dateTime(p.updated_at)],
              ]}
            />
            {p.description && <p className="mt-4 whitespace-pre-wrap border-t border-slate-100 pt-4 text-sm text-slate-700">{p.description}</p>}
          </Card>
          <Card title={<span className="flex items-center gap-1.5"><Lock className="h-4 w-4" /> Informations confidentielles</span>}>
            {p.confidential_visible ? (
              <KV
                cols={1}
                items={[
                  ["Adresse", p.address ?? "—"],
                  ["Coordonnées GPS", p.latitude && p.longitude ? <a key="m" className="text-brand-700 hover:underline" target="_blank" rel="noreferrer noopener" href={`https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=17/${p.latitude}/${p.longitude}`}>{p.latitude}, {p.longitude}</a> : "—"],
                  ["Propriétaire", p.owner ? `${p.owner.full_name}${p.owner.company ? " (" + p.owner.company + ")" : ""}` : "—"],
                  ["Contact propriétaire", p.owner ? `${p.owner.phone ?? "—"} · ${p.owner.email ?? "—"}` : "—"],
                  ["Notes internes", p.internal_notes ?? "—"],
                ]}
              />
            ) : (
              <p className="text-sm text-slate-500">Vous n'avez pas accès à l'adresse, au propriétaire ni aux notes internes de ce bien.</p>
            )}
          </Card>
        </div>
      )}
      {tab === "photos" && <PhotosTab p={p} />}
      {tab === "documents" && <DocumentsTab p={p} />}
      {tab === "matches" && <PropertyMatches propertyId={p.id} />}
      {tab === "visits" && <PropertyVisits propertyId={p.id} />}
      {tab === "history" && <HistoryTab propertyId={p.id} />}
      <StatusModal open={statusOpen} onClose={() => setStatusOpen(false)} p={p} />
    </>
  );
}

function StatusModal({ open, onClose, p }: { open: boolean; onClose: () => void; p: Property }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState(p.status);
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => api<Property>(`/properties/${p.id}/status`, { body: { status, reason: reason || null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["property", p.id] });
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.invalidateQueries({ queryKey: ["property-history", p.id] });
      toast.success("Statut mis à jour : les correspondances et le site public sont actualisés.");
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal open={open} onClose={onClose} title="Statut de disponibilité" footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Enregistrer</Button></>}>
      <div className="space-y-3">
        <Field label="Statut">{(id) => <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)} options={options(L.propertyStatus).filter((o) => o.value !== "archived" || can("properties.archive"))} />}</Field>
        <Field label="Motif (optionnel)">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} />}</Field>
        <p className="text-xs text-slate-500">Pour une vente ou location conclue avec un client, utilisez plutôt le module Ventes & locations : il met à jour le bien, la demande et la commission.</p>
      </div>
    </Modal>
  );
}

function PhotosTab({ p }: { p: Property }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["property", p.id] });
  const upload = useMutation({
    mutationFn: (files: FileList) => {
      const fd = new FormData();
      Array.from(files).forEach((f) => fd.append("files", f));
      return api(`/properties/${p.id}/photos`, { form: fd });
    },
    onSuccess: () => {
      refresh();
      toast.success("Photos ajoutées.");
    },
    onError: toast.error,
  });
  const del = useMutation({ mutationFn: (pid: string) => api(`/properties/${p.id}/photos/${pid}`, { method: "DELETE" }), onSuccess: refresh, onError: toast.error });
  const cover = useMutation({
    mutationFn: (pid: string) => api(`/properties/${p.id}/photos/order`, { method: "PUT", body: [pid, ...p.photos.filter((x) => x.id !== pid).map((x) => x.id)] }),
    onSuccess: refresh,
    onError: toast.error,
  });
  return (
    <Card
      title="Photos"
      actions={
        can("properties.edit") && (
          <>
            <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(e) => e.target.files?.length && upload.mutate(e.target.files)} />
            <Button size="sm" icon={<ImagePlus className="h-4 w-4" />} loading={upload.isPending} onClick={() => input.current?.click()}>
              Ajouter des photos
            </Button>
          </>
        )
      }
    >
      {!p.photos.length ? (
        <EmptyState title="Aucune photo" icon={<Building2 className="h-10 w-10" />}>JPEG, PNG ou WebP — 15 Mo max par fichier.</EmptyState>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {p.photos.map((ph, idx) => (
            <figure key={ph.id} className="group relative overflow-hidden rounded-lg border border-slate-200">
              <img src={ph.url} alt={ph.filename} className="aspect-[4/3] w-full object-cover" loading="lazy" />
              {idx === 0 && <span className="absolute left-2 top-2 rounded bg-gold-500 px-1.5 py-0.5 text-xs font-medium text-brand-950">Couverture</span>}
              {can("properties.edit") && (
                <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-gradient-to-t from-black/60 to-transparent p-2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                  {idx !== 0 && (
                    <button onClick={() => cover.mutate(ph.id)} className="rounded bg-white/90 p-1 text-slate-700" aria-label="Définir comme couverture">
                      <Star className="h-4 w-4" />
                    </button>
                  )}
                  <button onClick={() => del.mutate(ph.id)} className="rounded bg-white/90 p-1 text-red-600" aria-label="Supprimer la photo">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </figure>
          ))}
        </div>
      )}
    </Card>
  );
}

function DocumentsTab({ p }: { p: Property }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [label, setLabel] = useState("");
  const [confidential, setConfidential] = useState(true);
  const q = useQuery({ queryKey: ["documents", p.id], queryFn: () => api<Doc[]>(`/properties/${p.id}/documents`) });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      if (label) fd.append("label", label);
      fd.append("is_confidential", String(confidential));
      return api(`/properties/${p.id}/documents`, { form: fd });
    },
    onSuccess: () => {
      setLabel("");
      qc.invalidateQueries({ queryKey: ["documents", p.id] });
      toast.success("Document ajouté.");
    },
    onError: toast.error,
  });
  const del = useMutation({ mutationFn: (d: string) => api(`/properties/${p.id}/documents/${d}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", p.id] }), onError: toast.error });
  const canUpload = can("properties.edit", "properties.view_confidential");
  return (
    <Card title="Documents et pièces justificatives">
      {canUpload && (
        <div className="mb-4 flex flex-col gap-2 rounded-lg bg-slate-50 p-3 sm:flex-row sm:items-center">
          <Input placeholder="Libellé (ex. Titre foncier, plan…)" value={label} onChange={(e) => setLabel(e.target.value)} className="sm:max-w-xs" aria-label="Libellé du document" />
          <Checkbox label="Confidentiel" checked={confidential} onChange={setConfidential} />
          <input ref={input} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          <Button size="sm" icon={<Upload className="h-4 w-4" />} loading={upload.isPending} onClick={() => input.current?.click()}>
            Téléverser (PDF / image)
          </Button>
        </div>
      )}
      {!q.data?.length ? (
        <EmptyState title="Aucun document accessible" icon={<FileText className="h-10 w-10" />} />
      ) : (
        <ul className="divide-y divide-slate-100">
          {q.data.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <FileText className="h-4 w-4 text-slate-400" />
              <span className="flex-1 truncate">
                {d.label ?? d.filename} <span className="text-xs text-slate-500">· {(d.size / 1024).toFixed(0)} Ko · {date(d.created_at)}</span>
              </span>
              {d.is_confidential && <Badge color="red"><Lock className="h-3 w-3" /> Confidentiel</Badge>}
              <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={() => download(`/files/documents/${d.id}`).catch(toast.error)}>
                Télécharger
              </Button>
              {canUpload && (
                <ConfirmButton size="sm" variant="ghost" danger icon={<Trash2 className="h-3.5 w-3.5" />} title="Supprimer le document" message={`Supprimer définitivement « ${d.label ?? d.filename} » ?`} confirmLabel="Supprimer" onConfirm={() => del.mutateAsync(d.id)}>
                  {""}
                </ConfirmButton>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PropertyMatches({ propertyId }: { propertyId: string }) {
  const q = useQuery({ queryKey: ["property-matches", propertyId], queryFn: () => api<Page<Match>>("/matches", { query: { property_id: propertyId, page_size: 100 } }) });
  return (
    <Card title="Clients dont la recherche correspond à ce bien">
      {q.isLoading ? (
        <Spinner />
      ) : !q.data?.items.length ? (
        <EmptyState title="Aucune demande correspondante (dans votre périmètre)" />
      ) : (
        <ul className="divide-y divide-slate-100">
          {q.data.items.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <Link to={`/app/requests/${m.request_id}`} className="min-w-0 flex-1 font-medium text-brand-800 hover:underline">
                {m.customer_name} <span className="font-normal text-slate-500">· {m.request_reference}</span>
              </Link>
              <MatchBadge category={m.category} />
              <ScoreBar score={m.score} category={m.category} />
              <span className="text-xs text-slate-500">{m.agent?.full_name ?? "Non assignée"}</span>
              {m.status && m.status !== "suggested" && <Badge color="violet">{L.matchStatus[m.status]}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PropertyVisits({ propertyId }: { propertyId: string }) {
  const q = useQuery({ queryKey: ["visits", "property", propertyId], queryFn: () => api<Page<Visit>>("/visits", { query: { property_id: propertyId, order: "desc" } }) });
  return (
    <Card title="Visites">
      {!q.data?.items.length ? (
        <EmptyState title="Aucune visite" />
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {q.data.items.map((v) => (
            <li key={v.id} className="flex flex-wrap justify-between gap-2 py-2">
              <span>
                {dateTime(v.scheduled_at)} · {v.customer_name} {v.agent && <span className="text-slate-500">· {v.agent.full_name}</span>}
              </span>
              <Badge>{L.visitStatus[v.status]}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ") || "—";
  if (typeof v === "boolean") return v ? "oui" : "non";
  return L.propertyStatus[String(v)] ?? String(v);
}

function HistoryTab({ propertyId }: { propertyId: string }) {
  const q = useQuery({
    queryKey: ["property-history", propertyId],
    queryFn: () => api<{ id: number; action: string; user: string | null; created_at: string; changes: Record<string, unknown> }[]>(`/properties/${propertyId}/history`),
  });
  return (
    <Card title="Historique du bien">
      {!q.data?.length ? (
        <EmptyState title="Aucun historique" />
      ) : (
        <ol className="space-y-3">
          {q.data.map((h) => (
            <li key={h.id} className="rounded-lg border border-slate-100 p-3 text-sm">
              <p className="text-xs text-slate-500">
                {dateTime(h.created_at)} · {h.user ?? "Système"} · <strong className="text-slate-700">{ACTION_LABELS[h.action] ?? h.action}</strong>
              </p>
              <ul className="mt-1 space-y-0.5">
                {Object.entries(h.changes ?? {}).map(([k, v]) => (
                  <li key={k} className="text-slate-700">
                    <span className="text-slate-500">{FIELD_LABELS[k] ?? k} : </span>
                    {v && typeof v === "object" && "old" in (v as object) ? (
                      <>
                        <span className="line-through decoration-slate-400">{fmtVal((v as { old: unknown }).old)}</span> → <span className="font-medium">{fmtVal((v as { new: unknown }).new)}</span>
                      </>
                    ) : (
                      fmtVal(v)
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

