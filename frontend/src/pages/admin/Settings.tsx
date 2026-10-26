import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Checkbox, ErrorState, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { money } from "../../lib/format";
import { useCatalog } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";

type Json = Record<string, unknown>;
interface AllSettings {
  agency: { name: string; phone: string; email: string; address: string; default_currency: string };
  matching: {
    eligible_statuses: string[];
    neighborhood_mandatory: boolean;
    budget_tolerance_percent: number;
    surface_tolerance_percent: number;
    bedrooms_mandatory: boolean;
    notify_min_category: string;
    strong_threshold: number;
    weights: Record<string, number>;
  };
  deals: { mark_under_negotiation: boolean; close_competing_deals: boolean };
  reminders: { visit_reminder_hours: number; overdue_follow_up_enabled: boolean };
  public_site: { enabled: boolean; show_price: boolean };
  integrations: { smtp_configured: boolean; storage_backend: string; whatsapp_configured: boolean };
}
interface Rule {
  id: string;
  name: string;
  transaction_type: string;
  property_type: string | null;
  min_price: string | null;
  max_price: string | null;
  rate_percent: string;
  fixed_amount: string;
  priority: number;
  is_active: boolean;
}

const WEIGHT_LABELS: Record<string, string> = { neighborhood: "Quartier", price_fit: "Prix dans la fourchette", surface_fit: "Surface dans la fourchette", bathrooms: "Salles de bain", preferred_features: "Équipements souhaités" };

export default function SettingsPage() {
  const [tab, setTab] = useState<"matching" | "agency" | "catalog" | "commissions">("matching");
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api<AllSettings>("/settings") });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <>
      <PageHeader title="Paramètres" subtitle="Règles métier configurables. Chaque modification est tracée dans le journal d'audit." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "matching", label: "Moteur de correspondance" }, { value: "agency", label: "Agence & fonctionnement" }, { value: "catalog", label: "Types & équipements" }, { value: "commissions", label: "Commissions" }]} />
      {tab === "matching" && <MatchingSettings s={q.data!.matching} />}
      {tab === "agency" && <AgencySettings s={q.data!} />}
      {tab === "catalog" && <CatalogSettings />}
      {tab === "commissions" && <CommissionSettings />}
    </>
  );
}

function useSaveSetting(key: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (value: Json) => api(`/settings/${key}`, { method: "PUT", body: { value } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(key === "matching" ? "Règles enregistrées — toutes les correspondances ont été recalculées." : "Paramètres enregistrés.");
    },
    onError: toast.error,
  });
}

function MatchingSettings({ s }: { s: AllSettings["matching"] }) {
  const [m, setM] = useState(s);
  useEffect(() => setM(s), [s]);
  const save = useSaveSetting("matching");
  const total = Object.values(m.weights).reduce((a, b) => a + Number(b), 0);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Critères obligatoires">
        <p className="mb-3 text-sm text-slate-600">Type de transaction, type de bien, ville, devise, budget maximum, surface minimum et équipements obligatoires sont toujours vérifiés. Un bien qui échoue n'est jamais proposé comme correspondance.</p>
        <div className="space-y-3">
          <Field label="Statuts de bien éligibles">
            {() => (
              <div className="flex flex-wrap gap-3">
                {Object.entries(L.propertyStatus).filter(([k]) => !["sold", "rented", "archived"].includes(k)).map(([k, label]) => (
                  <Checkbox key={k} label={label} checked={m.eligible_statuses.includes(k)} onChange={(v) => setM({ ...m, eligible_statuses: v ? [...m.eligible_statuses, k] : m.eligible_statuses.filter((x) => x !== k) })} />
                ))}
              </div>
            )}
          </Field>
          <Checkbox label="Le quartier est obligatoire (sinon : correspondance partielle si autre quartier de la même ville)" checked={m.neighborhood_mandatory} onChange={(v) => setM({ ...m, neighborhood_mandatory: v })} />
          <Checkbox label="Le nombre minimum de chambres est obligatoire" checked={m.bedrooms_mandatory} onChange={(v) => setM({ ...m, bedrooms_mandatory: v })} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Tolérance budget (%)" hint="0 = tout dépassement exclut le bien. Au-delà de 0, un bien légèrement plus cher reste au mieux « partiel ».">{(id) => <Input id={id} type="number" min={0} max={50} value={m.budget_tolerance_percent} onChange={(e) => setM({ ...m, budget_tolerance_percent: Number(e.target.value) })} />}</Field>
            <Field label="Tolérance surface (%)">{(id) => <Input id={id} type="number" min={0} max={50} value={m.surface_tolerance_percent} onChange={(e) => setM({ ...m, surface_tolerance_percent: Number(e.target.value) })} />}</Field>
          </div>
        </div>
      </Card>
      <Card title="Score et notifications">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Seuil « forte correspondance »">{(id) => <Input id={id} type="number" min={50} max={100} value={m.strong_threshold} onChange={(e) => setM({ ...m, strong_threshold: Number(e.target.value) })} />}</Field>
          <Field label="Notifier l'agent à partir de">{(id) => <Select id={id} value={m.notify_min_category} onChange={(e) => setM({ ...m, notify_min_category: e.target.value })} options={[{ value: "exact", label: "Exacte" }, { value: "strong", label: "Forte" }, { value: "partial", label: "Partielle" }]} />}</Field>
        </div>
        <p className="mb-2 mt-4 text-sm font-medium text-slate-700">Poids des préférences (total = 50 ; les critères obligatoires valent 50)</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {Object.entries(m.weights).map(([k, v]) => (
            <Field key={k} label={WEIGHT_LABELS[k] ?? k}>{(id) => <Input id={id} type="number" min={0} max={50} value={v} onChange={(e) => setM({ ...m, weights: { ...m.weights, [k]: Number(e.target.value) } })} />}</Field>
          ))}
        </div>
        <p className={`mt-2 text-xs ${total === 50 ? "text-emerald-700" : "text-red-600"}`}>Total : {total} / 50</p>
      </Card>
      <div className="lg:col-span-2 flex justify-end">
        <Button loading={save.isPending} disabled={total !== 50 || !m.eligible_statuses.length} onClick={() => save.mutate(m as unknown as Json)}>
          Enregistrer et recalculer
        </Button>
      </div>
    </div>
  );
}

function AgencySettings({ s }: { s: AllSettings }) {
  const [agency, setAgency] = useState(s.agency);
  const [deals, setDeals] = useState(s.deals);
  const [rem, setRem] = useState(s.reminders);
  const [pub, setPub] = useState(s.public_site);
  const a = useSaveSetting("agency");
  const d = useSaveSetting("deals");
  const r = useSaveSetting("reminders");
  const p = useSaveSetting("public_site");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Agence" actions={<Button size="sm" loading={a.isPending} onClick={() => a.mutate(agency)}>Enregistrer</Button>}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nom">{(id) => <Input id={id} value={agency.name} onChange={(e) => setAgency({ ...agency, name: e.target.value })} />}</Field>
          <Field label="Devise par défaut">{(id) => <Input id={id} maxLength={3} value={agency.default_currency} onChange={(e) => setAgency({ ...agency, default_currency: e.target.value.toUpperCase() })} />}</Field>
          <Field label="Téléphone">{(id) => <Input id={id} value={agency.phone} onChange={(e) => setAgency({ ...agency, phone: e.target.value })} />}</Field>
          <Field label="E-mail">{(id) => <Input id={id} value={agency.email} onChange={(e) => setAgency({ ...agency, email: e.target.value })} />}</Field>
          <Field label="Adresse" className="sm:col-span-2">{(id) => <Input id={id} value={agency.address} onChange={(e) => setAgency({ ...agency, address: e.target.value })} />}</Field>
        </div>
      </Card>
      <Card title="Site public" actions={<Button size="sm" loading={p.isPending} onClick={() => p.mutate(pub)}>Enregistrer</Button>}>
        <div className="space-y-2">
          <Checkbox label="Site public activé (biens publiés et disponibles uniquement)" checked={pub.enabled} onChange={(v) => setPub({ ...pub, enabled: v })} />
          <Checkbox label="Afficher les prix sur le site public" checked={pub.show_price} onChange={(v) => setPub({ ...pub, show_price: v })} />
        </div>
      </Card>
      <Card title="Transactions" actions={<Button size="sm" loading={d.isPending} onClick={() => d.mutate(deals)}>Enregistrer</Button>}>
        <div className="space-y-2">
          <Checkbox label="Passer un bien disponible « en négociation » à l'ouverture d'une transaction" checked={deals.mark_under_negotiation} onChange={(v) => setDeals({ ...deals, mark_under_negotiation: v })} />
          <Checkbox label="Clôturer automatiquement les négociations concurrentes quand un bien est vendu/loué" checked={deals.close_competing_deals} onChange={(v) => setDeals({ ...deals, close_competing_deals: v })} />
        </div>
      </Card>
      <Card title="Rappels" actions={<Button size="sm" loading={r.isPending} onClick={() => r.mutate(rem)}>Enregistrer</Button>}>
        <div className="space-y-3">
          <Checkbox label="Notifier les relances client en retard" checked={rem.overdue_follow_up_enabled} onChange={(v) => setRem({ ...rem, overdue_follow_up_enabled: v })} />
          <Field label="Rappel de visite (heures avant)">{(id) => <Input id={id} type="number" min={1} max={168} value={rem.visit_reminder_hours} onChange={(e) => setRem({ ...rem, visit_reminder_hours: Number(e.target.value) })} />}</Field>
        </div>
      </Card>
      <Card title="Intégrations" className="lg:col-span-2">
        <ul className="space-y-2 text-sm">
          <li className="flex items-center gap-2">E-mail (SMTP) : {s.integrations.smtp_configured ? <Badge color="green">configuré</Badge> : <Badge color="amber">non configuré — aucune notification e-mail n'est envoyée</Badge>}</li>
          <li className="flex items-center gap-2">WhatsApp / SMS : <Badge>non configuré — prévu via un fournisseur agréé</Badge></li>
          <li className="flex items-center gap-2">Stockage des fichiers : <Badge color="teal">{s.integrations.storage_backend === "s3" ? "Objet S3" : "Disque local"}</Badge></li>
        </ul>
        <p className="mt-2 text-xs text-slate-500">Ces intégrations se configurent par variables d'environnement sur le serveur (voir README).</p>
      </Card>
    </div>
  );
}

function CatalogSettings() {
  const { data, refetch } = useCatalog();
  const toast = useToast();
  const [kind, setKind] = useState<"property-types" | "features" | null>(null);
  const [item, setItem] = useState({ code: "", label: "", is_active: true, sort_order: 0, has_rooms: true });
  const save = useMutation({
    mutationFn: () => api(`/settings/${kind}`, { method: "PUT", body: kind === "features" ? { code: item.code, label: item.label, is_active: item.is_active, sort_order: item.sort_order } : item }),
    onSuccess: () => {
      refetch();
      setKind(null);
      toast.success("Catalogue mis à jour.");
    },
    onError: toast.error,
  });
  const open = (k: typeof kind, it?: Partial<typeof item>) => {
    setItem({ code: "", label: "", is_active: true, sort_order: 0, has_rooms: true, ...it });
    setKind(k);
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Types de biens" actions={<Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => open("property-types")}>Ajouter</Button>}>
        <ul className="divide-y divide-slate-100 text-sm">
          {data?.property_types.map((t) => (
            <li key={t.code} className="flex items-center justify-between py-2">
              <span>{t.label} <span className="font-mono text-xs text-slate-400">{t.code}</span> {!t.is_active && <Badge>inactif</Badge>}</span>
              <Button size="sm" variant="ghost" onClick={() => open("property-types", t)}>Modifier</Button>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Équipements" actions={<Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => open("features")}>Ajouter</Button>}>
        <ul className="divide-y divide-slate-100 text-sm">
          {data?.features.map((f) => (
            <li key={f.code} className="flex items-center justify-between py-2">
              <span>{f.label} <span className="font-mono text-xs text-slate-400">{f.code}</span> {!f.is_active && <Badge>inactif</Badge>}</span>
              <Button size="sm" variant="ghost" onClick={() => open("features", f)}>Modifier</Button>
            </li>
          ))}
        </ul>
      </Card>
      {kind && (
        <Modal open onClose={() => setKind(null)} title={kind === "features" ? "Équipement" : "Type de bien"} footer={<><Button variant="secondary" onClick={() => setKind(null)}>Annuler</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Enregistrer</Button></>}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Code" hint="minuscules, chiffres et _ (non modifiable ensuite)">{(id) => <Input id={id} value={item.code} onChange={(e) => setItem({ ...item, code: e.target.value })} />}</Field>
            <Field label="Libellé">{(id) => <Input id={id} value={item.label} onChange={(e) => setItem({ ...item, label: e.target.value })} />}</Field>
            <Field label="Ordre d'affichage">{(id) => <Input id={id} type="number" value={item.sort_order} onChange={(e) => setItem({ ...item, sort_order: Number(e.target.value) })} />}</Field>
          </div>
          <div className="mt-3 space-y-2">
            <Checkbox label="Actif" checked={item.is_active} onChange={(v) => setItem({ ...item, is_active: v })} />
            {kind === "property-types" && <Checkbox label="Comporte des pièces (chambres, salles de bain)" checked={item.has_rooms} onChange={(v) => setItem({ ...item, has_rooms: v })} />}
          </div>
        </Modal>
      )}
    </div>
  );
}

function CommissionSettings() {
  const { can } = useAuth();
  const { typeLabel, data: catalog } = useCatalog();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["commission-rules"], queryFn: () => api<Rule[]>("/commission-rules") });
  const [edit, setEdit] = useState<Partial<Rule> | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const body = { ...edit, property_type: edit?.property_type || null, min_price: edit?.min_price || null, max_price: edit?.max_price || null, fixed_amount: edit?.fixed_amount || "0" };
      delete (body as Partial<Rule>).id;
      return edit?.id ? api(`/commission-rules/${edit.id}`, { method: "PUT", body }) : api("/commission-rules", { body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["commission-rules"] });
      setEdit(null);
      toast.success("Règle enregistrée. Elle s'applique aux nouvelles transactions et aux prochains recalculs.");
    },
    onError: toast.error,
  });
  return (
    <Card title="Règles de commission" actions={can("commissions.manage") && <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setEdit({ name: "", transaction_type: "sale", rate_percent: "2.5", fixed_amount: "0", priority: 0, is_active: true })}>Nouvelle règle</Button>}>
      <Alert color="blue">La règle active la plus prioritaire correspondant au type de transaction, au type de bien et à la tranche de prix s'applique. Commission = prix × taux + montant fixe.</Alert>
      <ul className="mt-3 divide-y divide-slate-100 text-sm">
        {q.data?.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 py-2.5">
            <span className="min-w-0 flex-1">
              <strong>{r.name}</strong> {!r.is_active && <Badge>inactive</Badge>}
              <span className="block text-xs text-slate-500">
                {L.transaction[r.transaction_type]} · {r.property_type ? typeLabel(r.property_type) : "tous types"} · {r.min_price || r.max_price ? `${money(r.min_price ?? 0)} – ${r.max_price ? money(r.max_price) : "∞"}` : "tous prix"} · priorité {r.priority}
              </span>
            </span>
            <span className="font-semibold">{Number(r.rate_percent)} %{Number(r.fixed_amount) ? ` + ${money(r.fixed_amount)}` : ""}</span>
            {can("commissions.manage") && <Button size="sm" variant="ghost" onClick={() => setEdit(r)}>Modifier</Button>}
          </li>
        ))}
      </ul>
      {edit && (
        <Modal open onClose={() => setEdit(null)} title="Règle de commission" footer={<><Button variant="secondary" onClick={() => setEdit(null)}>Annuler</Button><Button loading={save.isPending} disabled={!edit.name} onClick={() => save.mutate()}>Enregistrer</Button></>}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Nom" className="sm:col-span-2">{(id) => <Input id={id} value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />}</Field>
            <Field label="Transaction">{(id) => <Select id={id} value={edit.transaction_type} onChange={(e) => setEdit({ ...edit, transaction_type: e.target.value })} options={options(L.transaction)} />}</Field>
            <Field label="Type de bien">{(id) => <Select id={id} value={edit.property_type ?? ""} onChange={(e) => setEdit({ ...edit, property_type: e.target.value })} placeholder="Tous" options={(catalog?.property_types ?? []).map((t) => ({ value: t.code, label: t.label }))} />}</Field>
            <Field label="Prix min.">{(id) => <Input id={id} type="number" min={0} value={edit.min_price ?? ""} onChange={(e) => setEdit({ ...edit, min_price: e.target.value })} />}</Field>
            <Field label="Prix max.">{(id) => <Input id={id} type="number" min={0} value={edit.max_price ?? ""} onChange={(e) => setEdit({ ...edit, max_price: e.target.value })} />}</Field>
            <Field label="Taux (%)">{(id) => <Input id={id} type="number" min={0} max={100} step="0.001" value={edit.rate_percent ?? ""} onChange={(e) => setEdit({ ...edit, rate_percent: e.target.value })} />}</Field>
            <Field label="Montant fixe">{(id) => <Input id={id} type="number" min={0} value={edit.fixed_amount ?? ""} onChange={(e) => setEdit({ ...edit, fixed_amount: e.target.value })} />}</Field>
            <Field label="Priorité" hint="La plus élevée l'emporte.">{(id) => <Input id={id} type="number" value={edit.priority ?? 0} onChange={(e) => setEdit({ ...edit, priority: Number(e.target.value) })} />}</Field>
            <div className="flex items-end pb-2"><Checkbox label="Active" checked={edit.is_active ?? true} onChange={(v) => setEdit({ ...edit, is_active: v })} /></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}
