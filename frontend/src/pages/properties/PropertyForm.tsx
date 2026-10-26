import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FeaturePicker, useOptionsFromCatalog } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Button, Card, Checkbox, Field, Input, PageHeader, Select, Spinner, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCatalog, useDirectory } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Owner, Property } from "../../lib/types";

const EMPTY = {
  property_type: "apartment", transaction_type: "sale", title: "", description: "", city: "", neighborhood: "", address: "",
  surface: "", price: "", currency: "MAD", bedrooms: "", bathrooms: "", floor: "", latitude: "", longitude: "", internal_notes: "",
  responsible_id: "", status: "available",
};
type Form = typeof EMPTY;
const n = (v: string) => (v === "" ? null : v);
const i = (v: string) => (v === "" ? null : Number(v));

export default function PropertyForm() {
  const { id } = useParams();
  const editing = !!id;
  const { can } = useAuth();
  const conf = can("properties.view_confidential");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: catalog } = useCatalog();
  const { types } = useOptionsFromCatalog();
  const staff = useDirectory();
  const [f, setF] = useState<Form>({ ...EMPTY });
  const [features, setFeatures] = useState<string[]>([]);
  const [published, setPublished] = useState(false);
  const [ownerMode, setOwnerMode] = useState<"none" | "existing" | "new">("none");
  const [owner, setOwner] = useState<Owner | null>(null);
  const [ownerSearch, setOwnerSearch] = useState("");
  const [newOwner, setNewOwner] = useState({ full_name: "", phone: "", email: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (p: Partial<Form>) => setF((x) => ({ ...x, ...p }));

  const current = useQuery({ queryKey: ["property", id], queryFn: () => api<Property>(`/properties/${id}`), enabled: editing });
  useEffect(() => {
    const p = current.data;
    if (!p) return;
    setF({
      property_type: p.property_type, transaction_type: p.transaction_type, title: p.title, description: p.description ?? "", city: p.city,
      neighborhood: p.neighborhood ?? "", address: p.address ?? "", surface: p.surface ?? "", price: p.price, currency: p.currency,
      bedrooms: p.bedrooms?.toString() ?? "", bathrooms: p.bathrooms?.toString() ?? "", floor: p.floor?.toString() ?? "",
      latitude: p.latitude ?? "", longitude: p.longitude ?? "", internal_notes: p.internal_notes ?? "", responsible_id: p.responsible?.id ?? "", status: p.status,
    });
    setFeatures(p.features);
    setPublished(p.is_published);
    if (p.owner) {
      setOwner(p.owner);
      setOwnerMode("existing");
    }
  }, [current.data]);
  useEffect(() => {
    if (catalog && !editing) set({ currency: catalog.currency });
  }, [catalog, editing]);

  const owners = useQuery({
    queryKey: ["owners", ownerSearch],
    queryFn: () => api<Owner[]>("/owners", { query: { q: ownerSearch } }),
    enabled: conf && ownerMode === "existing" && !owner,
  });

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        property_type: f.property_type, transaction_type: f.transaction_type, title: f.title.trim(), description: n(f.description),
        city: f.city.trim(), neighborhood: n(f.neighborhood.trim()), surface: n(f.surface), price: f.price, currency: f.currency,
        bedrooms: i(f.bedrooms), bathrooms: i(f.bathrooms), floor: i(f.floor), features, responsible_id: n(f.responsible_id),
      };
      if (can("properties.publish")) body.is_published = published;
      if (conf) {
        Object.assign(body, { address: n(f.address), latitude: n(f.latitude), longitude: n(f.longitude), internal_notes: n(f.internal_notes) });
        if (ownerMode === "existing" && owner) body.owner_id = owner.id;
        if (ownerMode === "none") body.owner_id = null;
        if (ownerMode === "new" && !editing) body.owner = { full_name: newOwner.full_name, phone: n(newOwner.phone), email: n(newOwner.email) };
      }
      if (editing) return api<Property>(`/properties/${id}`, { method: "PATCH", body });
      return api<Property>("/properties", { body: { ...body, status: f.status } });
    },
    onSuccess: async (p) => {
      if (editing && conf && ownerMode === "new" && newOwner.full_name) {
        const o = await api<Owner>("/owners", { body: { full_name: newOwner.full_name, phone: n(newOwner.phone), email: n(newOwner.email) } });
        await api(`/properties/${p.id}`, { method: "PATCH", body: { owner_id: o.id } });
      }
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.invalidateQueries({ queryKey: ["property", p.id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(
        editing
          ? "Bien mis à jour — correspondances recalculées."
          : p.active_match_count
            ? `Bien créé : ${p.active_match_count} demande(s) client correspondent, les agents ont été notifiés.`
            : "Bien créé. Aucune demande en attente ne correspond pour l'instant.",
      );
      navigate(`/app/properties/${p.id}`);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Erreur"),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!f.title.trim() || !f.city.trim() || !f.price) return setError("Titre, ville et prix sont obligatoires.");
    if (ownerMode === "new" && !newOwner.full_name.trim()) return setError("Nom du propriétaire requis.");
    save.mutate();
  };

  if (editing && current.isLoading) return <Spinner />;
  const rooms = catalog?.property_types.find((t) => t.code === f.property_type)?.has_rooms ?? true;

  return (
    <>
      <PageHeader back={<BackLink to={editing ? `/app/properties/${id}` : "/app/properties"}>{editing ? "Retour au bien" : "Biens"}</BackLink>} title={editing ? `Modifier ${current.data?.reference}` : "Nouveau bien"} />
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Alert color="red">{error}</Alert>}
        <Card title="Description">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Type" required>{(id) => <Select id={id} value={f.property_type} onChange={(e) => set({ property_type: e.target.value })} options={types} />}</Field>
            <Field label="Transaction" required>{(id) => <Select id={id} value={f.transaction_type} onChange={(e) => set({ transaction_type: e.target.value })} options={options(L.transaction)} />}</Field>
            <Field label="Titre" required className="sm:col-span-2">{(id) => <Input id={id} value={f.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} />}</Field>
          </div>
          <Field label="Description" className="mt-3">{(id) => <Textarea id={id} rows={4} value={f.description} onChange={(e) => set({ description: e.target.value })} />}</Field>
        </Card>
        <Card title="Localisation">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Ville" required>
              {(id) => (
                <>
                  <Input id={id} list="cities-p" value={f.city} onChange={(e) => set({ city: e.target.value })} />
                  <datalist id="cities-p">{catalog?.cities.map((c) => <option key={c} value={c} />)}</datalist>
                </>
              )}
            </Field>
            <Field label="Quartier">{(id) => <Input id={id} value={f.neighborhood} onChange={(e) => set({ neighborhood: e.target.value })} />}</Field>
            {conf && (
              <>
                <Field label="Adresse (confidentielle)" className="sm:col-span-2">{(id) => <Input id={id} value={f.address} onChange={(e) => set({ address: e.target.value })} />}</Field>
                <Field label="Latitude">{(id) => <Input id={id} type="number" step="0.000001" value={f.latitude} onChange={(e) => set({ latitude: e.target.value })} />}</Field>
                <Field label="Longitude">{(id) => <Input id={id} type="number" step="0.000001" value={f.longitude} onChange={(e) => set({ longitude: e.target.value })} />}</Field>
              </>
            )}
          </div>
        </Card>
        <Card title="Caractéristiques et prix">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Prix" required>{(id) => <Input id={id} type="number" min={0} step="1000" value={f.price} onChange={(e) => set({ price: e.target.value })} />}</Field>
            <Field label="Devise">{(id) => <Input id={id} value={f.currency} maxLength={3} onChange={(e) => set({ currency: e.target.value.toUpperCase() })} />}</Field>
            <Field label="Surface (m²)">{(id) => <Input id={id} type="number" min={1} value={f.surface} onChange={(e) => set({ surface: e.target.value })} />}</Field>
            {rooms && (
              <>
                <Field label="Étage">{(id) => <Input id={id} type="number" value={f.floor} onChange={(e) => set({ floor: e.target.value })} />}</Field>
                <Field label="Chambres">{(id) => <Input id={id} type="number" min={0} value={f.bedrooms} onChange={(e) => set({ bedrooms: e.target.value })} />}</Field>
                <Field label="Salles de bain">{(id) => <Input id={id} type="number" min={0} value={f.bathrooms} onChange={(e) => set({ bathrooms: e.target.value })} />}</Field>
              </>
            )}
          </div>
          <div className="mt-4">
            <FeaturePicker label="Équipements (ascenseur, parking, jardin, terrasse, piscine…)" value={features} onChange={setFeatures} />
          </div>
        </Card>
        {conf && (
          <Card title="Propriétaire / fournisseur (confidentiel)">
            <div className="mb-3 flex flex-wrap gap-2">
              {(["none", "existing", "new"] as const).map((m) => (
                <Button key={m} size="sm" variant={ownerMode === m ? "primary" : "secondary"} onClick={() => setOwnerMode(m)} aria-pressed={ownerMode === m}>
                  {{ none: "Aucun", existing: "Propriétaire existant", new: "Nouveau propriétaire" }[m]}
                </Button>
              ))}
            </div>
            {ownerMode === "existing" &&
              (owner ? (
                <div className="flex items-center justify-between rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
                  <span>
                    <strong>{owner.full_name}</strong> · {owner.phone ?? owner.email ?? ""}
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => setOwner(null)}>
                    Changer
                  </Button>
                </div>
              ) : (
                <>
                  <Input placeholder="Rechercher un propriétaire…" value={ownerSearch} onChange={(e) => setOwnerSearch(e.target.value)} aria-label="Rechercher un propriétaire" />
                  <ul className="mt-2 max-h-48 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
                    {owners.data?.map((o) => (
                      <li key={o.id}>
                        <button type="button" onClick={() => setOwner(o)} className="w-full px-3 py-2 text-left text-sm hover:bg-brand-50">
                          {o.full_name} · {o.phone ?? o.email ?? ""}
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              ))}
            {ownerMode === "new" && (
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Nom" required>{(id) => <Input id={id} value={newOwner.full_name} onChange={(e) => setNewOwner({ ...newOwner, full_name: e.target.value })} />}</Field>
                <Field label="Téléphone">{(id) => <Input id={id} value={newOwner.phone} onChange={(e) => setNewOwner({ ...newOwner, phone: e.target.value })} />}</Field>
                <Field label="E-mail">{(id) => <Input id={id} type="email" value={newOwner.email} onChange={(e) => setNewOwner({ ...newOwner, email: e.target.value })} />}</Field>
              </div>
            )}
          </Card>
        )}
        <Card title="Gestion">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {!editing && <Field label="Statut initial">{(id) => <Select id={id} value={f.status} onChange={(e) => set({ status: e.target.value })} options={options(L.propertyStatus).filter((o) => o.value !== "archived")} />}</Field>}
            <Field label="Responsable de l'annonce">{(id) => <Select id={id} value={f.responsible_id} onChange={(e) => set({ responsible_id: e.target.value })} placeholder="Moi" options={(staff.data ?? []).map((u) => ({ value: u.id, label: u.full_name }))} />}</Field>
            {can("properties.publish") && (
              <div className="flex items-end pb-2">
                <Checkbox label="Publier sur le site public" checked={published} onChange={setPublished} />
              </div>
            )}
          </div>
          {conf && <Field label="Notes internes (confidentielles)" className="mt-3">{(id) => <Textarea id={id} value={f.internal_notes} onChange={(e) => set({ internal_notes: e.target.value })} />}</Field>}
        </Card>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Annuler
          </Button>
          <Button type="submit" loading={save.isPending}>
            Enregistrer
          </Button>
        </div>
      </form>
    </>
  );
}
