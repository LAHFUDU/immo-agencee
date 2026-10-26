import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { FeaturePicker, useOptionsFromCatalog } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Button, Card, Field, Input, Modal, PageHeader, Select, Spinner, Textarea, useToast } from "../../components/ui";
import { api, ApiError, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { fromLocalInput, toLocalInput } from "../../lib/format";
import { useCatalog, useDirectory } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Customer, CustomerRequest, DuplicateCandidate } from "../../lib/types";

const EMPTY = {
  property_type: "apartment", transaction_type: "sale", city: "", neighborhood: "", budget_min: "", budget_max: "", currency: "MAD",
  surface_min: "", surface_max: "", bedrooms_min: "", bathrooms_min: "", comments: "", priority: "normal", source: "phone",
  assigned_agent_id: "", next_follow_up_at: "", internal_notes: "",
};
type Form = typeof EMPTY;
const CUSTOMER_EMPTY = { full_name: "", phone: "", email: "", preferred_contact: "phone" };

const n = (v: string) => (v === "" ? null : v);
const i = (v: string) => (v === "" ? null : Number(v));

export default function RequestForm() {
  const { id } = useParams();
  const [search] = useSearchParams();
  const presetCustomer = search.get("customer_id");
  const editing = !!id;
  const { can } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: catalog } = useCatalog();
  const { types } = useOptionsFromCatalog();
  const agents = useDirectory(true);

  const [f, setF] = useState<Form>({ ...EMPTY });
  const [req, setReq] = useState<string[]>([]);
  const [pref, setPref] = useState<string[]>([]);
  const [customerMode, setCustomerMode] = useState<"new" | "existing">("new");
  const [cust, setCust] = useState({ ...CUSTOMER_EMPTY });
  const [existing, setExisting] = useState<Customer | null>(null);
  const [custSearch, setCustSearch] = useState("");
  const [dups, setDups] = useState<DuplicateCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<Form>) => setF((x) => ({ ...x, ...patch }));

  const current = useQuery({ queryKey: ["request", id], queryFn: () => api<CustomerRequest>(`/requests/${id}`), enabled: editing });
  useEffect(() => {
    const r = current.data;
    if (!r) return;
    setF({
      property_type: r.property_type, transaction_type: r.transaction_type, city: r.city, neighborhood: r.neighborhood ?? "",
      budget_min: r.budget_min ?? "", budget_max: r.budget_max ?? "", currency: r.currency, surface_min: r.surface_min ?? "",
      surface_max: r.surface_max ?? "", bedrooms_min: r.bedrooms_min?.toString() ?? "", bathrooms_min: r.bathrooms_min?.toString() ?? "",
      comments: r.comments ?? "", priority: r.priority, source: r.source, assigned_agent_id: r.assigned_agent?.id ?? "",
      next_follow_up_at: toLocalInput(r.next_follow_up_at), internal_notes: r.internal_notes ?? "",
    });
    setReq(r.required_features);
    setPref(r.preferred_features);
  }, [current.data]);
  useEffect(() => {
    if (catalog && !editing) set({ currency: catalog.currency });
  }, [catalog, editing]);

  const preset = useQuery({
    queryKey: ["customer", presetCustomer],
    queryFn: () => api<{ customer: Customer }>(`/customers/${presetCustomer}`),
    enabled: !!presetCustomer && !editing,
  });
  useEffect(() => {
    if (preset.data) {
      setExisting(preset.data.customer);
      setCustomerMode("existing");
    }
  }, [preset.data]);

  const customers = useQuery({
    queryKey: ["customers-pick", custSearch],
    queryFn: () => api<Page<Customer>>("/customers", { query: { q: custSearch, page_size: 8 } }),
    enabled: customerMode === "existing" && custSearch.trim().length >= 2,
  });

  const criteria = () => ({
    property_type: f.property_type, transaction_type: f.transaction_type, city: f.city.trim(), neighborhood: n(f.neighborhood.trim()),
    budget_min: n(f.budget_min), budget_max: n(f.budget_max), currency: f.currency, surface_min: n(f.surface_min), surface_max: n(f.surface_max),
    bedrooms_min: i(f.bedrooms_min), bathrooms_min: i(f.bathrooms_min), required_features: req, preferred_features: pref.filter((x) => !req.includes(x)),
    comments: n(f.comments), priority: f.priority, next_follow_up_at: fromLocalInput(f.next_follow_up_at), internal_notes: n(f.internal_notes),
  });

  const save = useMutation({
    mutationFn: async (allowDuplicate: boolean) => {
      if (editing) return api<CustomerRequest>(`/requests/${id}`, { method: "PATCH", body: criteria() });
      const body = {
        ...criteria(),
        source: f.source,
        assigned_agent_id: n(f.assigned_agent_id),
        ...(customerMode === "existing" && existing
          ? { customer_id: existing.id }
          : { customer: { full_name: cust.full_name.trim(), phone: n(cust.phone.trim()), email: n(cust.email.trim()), preferred_contact: cust.preferred_contact, source: f.source } }),
      };
      return api<{ request: CustomerRequest; message: string; match_count: number }>("/requests", { body, query: { allow_duplicate_customer: allowDuplicate } });
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["requests"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (editing) {
        qc.invalidateQueries({ queryKey: ["request", id] });
        toast.success("Demande mise à jour. Les correspondances ont été recalculées.");
        navigate(`/app/requests/${id}`);
      } else {
        const r = res as { request: CustomerRequest; message: string; match_count: number };
        navigate(`/app/requests/${r.request.id}`, { state: { created: r.message, matchCount: r.match_count } });
      }
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && (e.detail as { duplicates?: DuplicateCandidate[] })?.duplicates) {
        setDups((e.detail as { duplicates: DuplicateCandidate[] }).duplicates);
        return;
      }
      setError(e instanceof Error ? e.message : "Erreur");
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!editing && customerMode === "new" && !cust.phone.trim() && !cust.email.trim()) return setError("Indiquez au moins un téléphone ou un e-mail pour le client.");
    if (!editing && customerMode === "existing" && !existing) return setError("Sélectionnez un client existant.");
    save.mutate(false);
  };

  if (editing && current.isLoading) return <Spinner />;
  const rooms = catalog?.property_types.find((t) => t.code === f.property_type)?.has_rooms ?? true;

  return (
    <>
      <PageHeader
        back={<BackLink to={editing ? `/app/requests/${id}` : "/app/requests"}>{editing ? "Retour à la demande" : "Demandes"}</BackLink>}
        title={editing ? `Modifier ${current.data?.reference}` : "Nouvelle demande client"}
        subtitle="La demande est toujours enregistrée, même si aucun bien ne correspond aujourd'hui."
      />
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Alert color="red">{error}</Alert>}
        {!editing && (
          <Card title="Client">
            <div className="mb-3 flex gap-2" role="radiogroup" aria-label="Type de client">
              <Button variant={customerMode === "new" ? "primary" : "secondary"} size="sm" onClick={() => setCustomerMode("new")} aria-pressed={customerMode === "new"}>
                Nouveau client
              </Button>
              <Button variant={customerMode === "existing" ? "primary" : "secondary"} size="sm" onClick={() => setCustomerMode("existing")} aria-pressed={customerMode === "existing"}>
                Client existant
              </Button>
            </div>
            {customerMode === "new" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Nom complet" required>{(id) => <Input id={id} value={cust.full_name} onChange={(e) => setCust({ ...cust, full_name: e.target.value })} required minLength={2} />}</Field>
                <Field label="Téléphone">{(id) => <Input id={id} type="tel" value={cust.phone} onChange={(e) => setCust({ ...cust, phone: e.target.value })} placeholder="06 12 34 56 78" />}</Field>
                <Field label="E-mail">{(id) => <Input id={id} type="email" value={cust.email} onChange={(e) => setCust({ ...cust, email: e.target.value })} />}</Field>
                <Field label="Moyen de contact préféré">{(id) => <Select id={id} value={cust.preferred_contact} onChange={(e) => setCust({ ...cust, preferred_contact: e.target.value })} options={options(L.contactMethod)} />}</Field>
              </div>
            ) : existing ? (
              <div className="flex items-center justify-between rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
                <span>
                  <strong>{existing.full_name}</strong> · {existing.reference} · {existing.phone ?? existing.email}
                </span>
                <Button variant="ghost" size="sm" onClick={() => setExisting(null)}>
                  Changer
                </Button>
              </div>
            ) : (
              <div>
                <Input placeholder="Rechercher par nom, téléphone ou référence…" value={custSearch} onChange={(e) => setCustSearch(e.target.value)} aria-label="Rechercher un client" />
                <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {customers.data?.items.map((c) => (
                    <li key={c.id}>
                      <button type="button" className="w-full px-3 py-2 text-left text-sm hover:bg-brand-50" onClick={() => setExisting(c)}>
                        <strong>{c.full_name}</strong> · {c.reference} · {c.phone ?? c.email}
                      </button>
                    </li>
                  ))}
                  {customers.data && customers.data.items.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">Aucun client trouvé.</li>}
                </ul>
              </div>
            )}
          </Card>
        )}

        <Card title="Recherche du client">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Type de bien" required>{(id) => <Select id={id} value={f.property_type} onChange={(e) => set({ property_type: e.target.value })} options={types} />}</Field>
            <Field label="Achat ou location" required>{(id) => <Select id={id} value={f.transaction_type} onChange={(e) => set({ transaction_type: e.target.value })} options={options(L.transactionWish)} />}</Field>
            <Field label="Ville" required>
              {(id) => (
                <>
                  <Input id={id} list="cities" value={f.city} onChange={(e) => set({ city: e.target.value })} required />
                  <datalist id="cities">{catalog?.cities.map((c) => <option key={c} value={c} />)}</datalist>
                </>
              )}
            </Field>
            <Field label="Quartier(s)" hint="Plusieurs quartiers : séparez-les par des virgules.">{(id) => <Input id={id} value={f.neighborhood} onChange={(e) => set({ neighborhood: e.target.value })} />}</Field>
            <Field label="Budget minimum">{(id) => <Input id={id} type="number" min={0} step="1000" value={f.budget_min} onChange={(e) => set({ budget_min: e.target.value })} />}</Field>
            <Field label="Budget maximum" hint="Critère obligatoire pour la correspondance.">{(id) => <Input id={id} type="number" min={0} step="1000" value={f.budget_max} onChange={(e) => set({ budget_max: e.target.value })} />}</Field>
            <Field label="Devise">{(id) => <Input id={id} value={f.currency} maxLength={3} onChange={(e) => set({ currency: e.target.value.toUpperCase() })} />}</Field>
            <div />
            <Field label="Surface min. (m²)">{(id) => <Input id={id} type="number" min={1} value={f.surface_min} onChange={(e) => set({ surface_min: e.target.value })} />}</Field>
            <Field label="Surface max. (m²)">{(id) => <Input id={id} type="number" min={1} value={f.surface_max} onChange={(e) => set({ surface_max: e.target.value })} />}</Field>
            {rooms && (
              <>
                <Field label="Chambres min.">{(id) => <Input id={id} type="number" min={0} value={f.bedrooms_min} onChange={(e) => set({ bedrooms_min: e.target.value })} />}</Field>
                <Field label="Salles de bain min.">{(id) => <Input id={id} type="number" min={0} value={f.bathrooms_min} onChange={(e) => set({ bathrooms_min: e.target.value })} />}</Field>
              </>
            )}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <FeaturePicker label="Équipements obligatoires" value={req} onChange={setReq} />
            <FeaturePicker label="Équipements souhaités (bonus de score)" value={pref} onChange={setPref} />
          </div>
          <Field label="Commentaires / exigences du client" className="mt-4">{(id) => <Textarea id={id} value={f.comments} onChange={(e) => set({ comments: e.target.value })} />}</Field>
        </Card>

        <Card title="Suivi">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Priorité">{(id) => <Select id={id} value={f.priority} onChange={(e) => set({ priority: e.target.value })} options={options(L.priority)} />}</Field>
            {!editing && <Field label="Source">{(id) => <Select id={id} value={f.source} onChange={(e) => set({ source: e.target.value })} options={options(L.source)} />}</Field>}
            {!editing && can("requests.assign") && (
              <Field label="Agent assigné">{(id) => <Select id={id} value={f.assigned_agent_id} onChange={(e) => set({ assigned_agent_id: e.target.value })} placeholder="Non assignée" options={(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))} />}</Field>
            )}
            <Field label="Prochaine relance">{(id) => <Input id={id} type="datetime-local" value={f.next_follow_up_at} onChange={(e) => set({ next_follow_up_at: e.target.value })} />}</Field>
          </div>
          <Field label="Notes internes" hint="Visibles uniquement par l'équipe." className="mt-3">{(id) => <Textarea id={id} value={f.internal_notes} onChange={(e) => set({ internal_notes: e.target.value })} />}</Field>
        </Card>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Annuler
          </Button>
          <Button type="submit" loading={save.isPending}>
            {editing ? "Enregistrer" : "Enregistrer la demande"}
          </Button>
        </div>
      </form>

      <Modal
        open={!!dups}
        onClose={() => setDups(null)}
        title="Client déjà existant ?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDups(null)}>
              Annuler
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setDups(null);
                save.mutate(true);
              }}
            >
              Créer un nouveau client quand même
            </Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-600">Des clients avec les mêmes coordonnées existent déjà. Rattacher la demande à l'un d'eux évite les doublons :</p>
        <ul className="space-y-2">
          {dups?.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <span>
                <strong>{d.full_name}</strong> · {d.reference} <span className="text-slate-500">({d.reason})</span>
              </span>
              <Button
                size="sm"
                onClick={() => {
                  setExisting({ id: d.id, reference: d.reference, full_name: d.full_name, phone: d.phone, email: d.email } as Customer);
                  setCustomerMode("existing");
                  setDups(null);
                }}
              >
                Utiliser
              </Button>
            </li>
          ))}
        </ul>
      </Modal>
    </>
  );
}
