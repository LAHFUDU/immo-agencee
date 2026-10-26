/** Optional public website: published & available properties, contact and property-request forms. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { BedDouble, Building2, CheckCircle2, Mail, MapPin, Phone, Ruler, Search } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Checkbox, EmptyState, ErrorState, Field, Input, Pagination, Select, Spinner, Textarea } from "../components/ui";
import { api, type Page } from "../lib/api";
import { money, num } from "../lib/format";
import { L, options } from "../lib/i18n";

interface PublicProperty {
  reference: string;
  property_type: string;
  transaction_type: "sale" | "rent";
  title: string;
  description: string | null;
  city: string;
  neighborhood: string | null;
  surface: string | null;
  price: string | null;
  currency: string;
  bedrooms: number | null;
  bathrooms: number | null;
  floor: number | null;
  features: string[];
  photos: string[];
}
interface PublicCatalog {
  property_types: { code: string; label: string }[];
  features: { code: string; label: string }[];
  cities: string[];
}
interface PublicConfig {
  agency: { name: string; phone: string; email: string; address: string };
  show_price: boolean;
}

const useConfig = () => useQuery({ queryKey: ["public-config"], queryFn: () => api<PublicConfig>("/public/config"), retry: false, staleTime: 300_000 });
const useCatalog = () => useQuery({ queryKey: ["public-catalog"], queryFn: () => api<PublicCatalog>("/public/catalog"), staleTime: 300_000 });

export function PublicLayout() {
  const cfg = useConfig();
  if (cfg.isError)
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div>
          <p className="text-lg font-semibold text-slate-800">Site momentanément indisponible.</p>
          <Link to="/login" className="mt-3 inline-block text-sm text-brand-700 hover:underline">Espace agence</Link>
        </div>
      </div>
    );
  const agency = cfg.data?.agency;
  const nav = ({ isActive }: { isActive: boolean }) => `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "text-gold-300" : "text-white/90 hover:text-white"}`;
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="bg-brand-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-auto flex items-center gap-2 text-white">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gold-500 text-brand-950"><Building2 className="h-5 w-5" /></span>
            <span className="font-semibold tracking-tight">{agency?.name ?? "Agence immobilière"}</span>
          </Link>
          <nav className="flex flex-wrap items-center" aria-label="Site public">
            <NavLink to="/" end className={nav}>Biens</NavLink>
            <NavLink to="/demande" className={nav}>Déposer une recherche</NavLink>
            <NavLink to="/contact" className={nav}>Contact</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-6 text-sm text-slate-600">
          <span className="font-medium text-slate-800">{agency?.name}</span>
          {agency?.address && <span className="flex items-center gap-1"><MapPin className="h-4 w-4" />{agency.address}</span>}
          {agency?.phone && <a href={`tel:${agency.phone}`} className="flex items-center gap-1 hover:text-brand-700"><Phone className="h-4 w-4" />{agency.phone}</a>}
          {agency?.email && <a href={`mailto:${agency.email}`} className="flex items-center gap-1 hover:text-brand-700"><Mail className="h-4 w-4" />{agency.email}</a>}
          <Link to="/login" className="ml-auto text-xs text-slate-400 hover:text-slate-600">Espace agence</Link>
        </div>
      </footer>
    </div>
  );
}

function PropertyCard({ p, showPrice, typeLabel }: { p: PublicProperty; showPrice: boolean; typeLabel: (c: string) => string }) {
  return (
    <Link to={`/biens/${p.reference}`} className="group overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
      <div className="relative aspect-[4/3] bg-slate-100">
        {p.photos[0] ? <img src={p.photos[0]} alt={p.title} className="h-full w-full object-cover" loading="lazy" /> : <div className="flex h-full items-center justify-center text-slate-300"><Building2 className="h-12 w-12" /></div>}
        <span className="absolute left-3 top-3 rounded-full bg-white/95 px-2.5 py-1 text-xs font-semibold text-brand-900">{L.transaction[p.transaction_type]}</span>
      </div>
      <div className="p-4">
        <p className="text-xs uppercase tracking-wide text-slate-500">{typeLabel(p.property_type)} · {p.city}{p.neighborhood ? ` / ${p.neighborhood}` : ""}</p>
        <h3 className="mt-1 line-clamp-2 font-semibold text-slate-900 group-hover:text-brand-700">{p.title}</h3>
        <div className="mt-2 flex flex-wrap gap-3 text-sm text-slate-600">
          {p.surface && <span className="flex items-center gap-1"><Ruler className="h-4 w-4" />{num(p.surface, " m²")}</span>}
          {p.bedrooms !== null && <span className="flex items-center gap-1"><BedDouble className="h-4 w-4" />{p.bedrooms} ch.</span>}
        </div>
        <p className="mt-3 text-lg font-semibold text-brand-800">{showPrice && p.price ? `${money(p.price, p.currency)}${p.transaction_type === "rent" ? " / mois" : ""}` : "Prix sur demande"}</p>
      </div>
    </Link>
  );
}

export function PublicHome() {
  const [params, setParams] = useSearchParams();
  const cfg = useConfig();
  const cat = useCatalog();
  const page = Number(params.get("page") ?? 1);
  const query = Object.fromEntries(params.entries());
  const q = useQuery({ queryKey: ["public-properties", query], queryFn: () => api<Page<PublicProperty>>("/public/properties", { query: { ...query, page_size: 12 } }) });
  const typeLabel = (c: string) => cat.data?.property_types.find((t) => t.code === c)?.label ?? c;
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("page");
    setParams(next);
  };
  return (
    <>
      <section className="mb-8 rounded-2xl bg-gradient-to-br from-brand-800 to-brand-600 px-6 py-10 text-white">
        <h1 className="text-2xl font-semibold sm:text-3xl">Trouvez le bien qui vous ressemble</h1>
        <p className="mt-2 max-w-xl text-brand-100">Appartements, maisons, villas, locaux et terrains, à l'achat comme à la location. Vous ne trouvez pas ? <Link to="/demande" className="font-medium text-gold-300 underline">Déposez votre recherche</Link>, nous vous prévenons dès qu'un bien correspond.</p>
        <div className="mt-6 grid gap-2 rounded-xl bg-white p-3 text-slate-800 sm:grid-cols-2 lg:grid-cols-5">
          <Select aria-label="Transaction" value={params.get("transaction_type") ?? ""} onChange={(e) => set("transaction_type", e.target.value)} placeholder="Achat ou location" options={[{ value: "sale", label: "Acheter" }, { value: "rent", label: "Louer" }]} />
          <Select aria-label="Type" value={params.get("property_type") ?? ""} onChange={(e) => set("property_type", e.target.value)} placeholder="Type de bien" options={(cat.data?.property_types ?? []).map((t) => ({ value: t.code, label: t.label }))} />
          <Select aria-label="Ville" value={params.get("city") ?? ""} onChange={(e) => set("city", e.target.value)} placeholder="Ville" options={(cat.data?.cities ?? []).map((c) => ({ value: c, label: c }))} />
          <Input aria-label="Budget maximum" type="number" min={0} placeholder="Budget max." value={params.get("price_max") ?? ""} onChange={(e) => set("price_max", e.target.value)} />
          <Input aria-label="Surface minimum" type="number" min={0} placeholder="Surface min. (m²)" value={params.get("surface_min") ?? ""} onChange={(e) => set("surface_min", e.target.value)} />
        </div>
      </section>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data?.items.length ? (
        <EmptyState title="Aucun bien ne correspond à vos critères" icon={<Search className="h-10 w-10" />}>
          <Link to="/demande" className="text-brand-700 underline">Déposez votre recherche</Link> : un conseiller vous contactera dès qu'un bien correspondant sera disponible.
        </EmptyState>
      ) : (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {q.data.items.map((p) => <PropertyCard key={p.reference} p={p} showPrice={cfg.data?.show_price ?? true} typeLabel={typeLabel} />)}
          </div>
          <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => { const n = new URLSearchParams(params); n.set("page", String(p)); setParams(n); }} />
        </>
      )}
    </>
  );
}

export function PublicPropertyPage() {
  const { reference } = useParams();
  const cfg = useConfig();
  const cat = useCatalog();
  const [photo, setPhoto] = useState(0);
  const q = useQuery({ queryKey: ["public-property", reference], queryFn: () => api<PublicProperty>(`/public/properties/${reference}`), retry: false });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <EmptyState title="Ce bien n'est plus disponible">Il a peut-être été vendu ou loué. <Link to="/" className="text-brand-700 underline">Voir les autres biens</Link></EmptyState>;
  const p = q.data!;
  const feature = (c: string) => cat.data?.features.find((f) => f.code === c)?.label ?? c;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="overflow-hidden rounded-2xl bg-slate-100">
          {p.photos.length ? <img src={p.photos[photo]} alt={p.title} className="aspect-[16/10] w-full object-cover" /> : <div className="flex aspect-[16/10] items-center justify-center text-slate-300"><Building2 className="h-16 w-16" /></div>}
        </div>
        {p.photos.length > 1 && (
          <div className="mt-2 flex gap-2 overflow-x-auto">
            {p.photos.map((u, i) => (
              <button key={u} onClick={() => setPhoto(i)} className={`h-16 w-20 shrink-0 overflow-hidden rounded-lg ring-2 ${i === photo ? "ring-brand-600" : "ring-transparent"}`} aria-label={`Photo ${i + 1}`}>
                <img src={u} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        )}
        <h1 className="mt-5 text-2xl font-semibold text-slate-900">{p.title}</h1>
        <p className="mt-1 flex items-center gap-1 text-slate-600"><MapPin className="h-4 w-4" />{p.city}{p.neighborhood ? ` / ${p.neighborhood}` : ""} · réf. {p.reference}</p>
        <div className="mt-4 flex flex-wrap gap-4 text-sm text-slate-700">
          {p.surface && <span>{num(p.surface, " m²")}</span>}
          {p.bedrooms !== null && <span>{p.bedrooms} chambre(s)</span>}
          {p.bathrooms !== null && <span>{p.bathrooms} salle(s) de bain</span>}
          {p.floor !== null && <span>Étage {p.floor}</span>}
        </div>
        {p.features.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{p.features.map((f) => <span key={f} className="rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-800">{feature(f)}</span>)}</div>}
        {p.description && <p className="mt-5 whitespace-pre-wrap text-slate-700">{p.description}</p>}
      </div>
      <aside className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">{L.transaction[p.transaction_type]}</p>
          <p className="text-2xl font-semibold text-brand-800">{cfg.data?.show_price && p.price ? `${money(p.price, p.currency)}${p.transaction_type === "rent" ? " / mois" : ""}` : "Prix sur demande"}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 font-semibold text-slate-900">Ce bien vous intéresse ?</h2>
          <ContactForm propertyReference={p.reference} compact />
        </div>
      </aside>
    </div>
  );
}

function Honeypot({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // Hidden from humans (and screen readers); bots that fill every field are silently ignored by the API.
  return (
    <div aria-hidden="true" style={{ position: "absolute", left: "-10000px", width: 1, height: 1, overflow: "hidden" }}>
      <label>Site web<input tabIndex={-1} autoComplete="off" value={value} onChange={(e) => onChange(e.target.value)} /></label>
    </div>
  );
}

function Success({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <CheckCircle2 className="h-10 w-10 text-emerald-600" />
      <p className="text-slate-700">{children}</p>
    </div>
  );
}

function ContactForm({ propertyReference, compact }: { propertyReference?: string; compact?: boolean }) {
  const [f, setF] = useState({ full_name: "", phone: "", email: "", message: propertyReference ? `Bonjour, je souhaite des informations sur le bien ${propertyReference}.` : "" });
  const [consent, setConsent] = useState(false);
  const [website, setWebsite] = useState("");
  const send = useMutation({ mutationFn: () => api<{ detail: string }>("/public/contact", { body: { ...f, phone: f.phone || null, email: f.email || null, property_reference: propertyReference ?? null, consent, website } }) });
  if (send.isSuccess) return <Success>{send.data.detail}</Success>;
  return (
    <form className="relative space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); send.mutate(); }}>
      {send.error && <Alert color="red">{send.error.message}</Alert>}
      <Honeypot value={website} onChange={setWebsite} />
      <Field label="Nom" required>{(id) => <Input id={id} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} required minLength={2} />}</Field>
      <div className={compact ? "space-y-3" : "grid gap-3 sm:grid-cols-2"}>
        <Field label="Téléphone">{(id) => <Input id={id} type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
        <Field label="E-mail">{(id) => <Input id={id} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
      </div>
      <Field label="Message" required>{(id) => <Textarea id={id} rows={compact ? 3 : 5} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} required minLength={5} />}</Field>
      <Checkbox label="J'accepte que l'agence utilise mes coordonnées pour répondre à ma demande." checked={consent} onChange={setConsent} />
      <Button type="submit" className="w-full" loading={send.isPending} disabled={!consent || f.full_name.trim().length < 2 || (!f.phone && !f.email) || f.message.trim().length < 5}>Envoyer</Button>
    </form>
  );
}

export function PublicContact() {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Nous contacter</h1>
      <ContactForm />
    </div>
  );
}

export function PublicRequest() {
  const cat = useCatalog();
  const [f, setF] = useState({ full_name: "", phone: "", email: "", preferred_contact: "phone", property_type: "apartment", transaction_type: "sale", city: "", neighborhood: "", budget_min: "", budget_max: "", surface_min: "", bedrooms_min: "", comments: "" });
  const [features, setFeatures] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [website, setWebsite] = useState("");
  const n = (v: string) => (v === "" ? null : v);
  const send = useMutation({
    mutationFn: () =>
      api<{ detail: string; reference: string | null }>("/public/requests", {
        body: { ...f, email: n(f.email), neighborhood: n(f.neighborhood), budget_min: n(f.budget_min), budget_max: n(f.budget_max), surface_min: n(f.surface_min), bedrooms_min: f.bedrooms_min ? Number(f.bedrooms_min) : null, comments: n(f.comments), features, consent, website },
      }),
  });
  if (send.isSuccess)
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <Success>
          {send.data.detail}
          {send.data.reference && <span className="mt-1 block text-sm text-slate-500">Référence de votre demande : {send.data.reference}</span>}
        </Success>
      </div>
    );
  return (
    <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold text-slate-900">Déposer votre recherche</h1>
      <p className="mb-5 mt-1 text-sm text-slate-600">Décrivez le bien que vous recherchez. Votre demande est conservée et un conseiller vous contacte dès qu'un bien correspondant est disponible.</p>
      <form className="relative space-y-4" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
        {send.error && <Alert color="red">{send.error.message}</Alert>}
        <Honeypot value={website} onChange={setWebsite} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nom complet" required>{(id) => <Input id={id} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />}</Field>
          <Field label="Téléphone" required>{(id) => <Input id={id} type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
          <Field label="E-mail">{(id) => <Input id={id} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
          <Field label="Moyen de contact préféré">{(id) => <Select id={id} value={f.preferred_contact} onChange={(e) => setF({ ...f, preferred_contact: e.target.value })} options={options(L.contactMethod)} />}</Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Je souhaite" required>{(id) => <Select id={id} value={f.transaction_type} onChange={(e) => setF({ ...f, transaction_type: e.target.value })} options={[{ value: "sale", label: "Acheter" }, { value: "rent", label: "Louer" }]} />}</Field>
          <Field label="Type de bien" required>{(id) => <Select id={id} value={f.property_type} onChange={(e) => setF({ ...f, property_type: e.target.value })} options={(cat.data?.property_types ?? []).map((t) => ({ value: t.code, label: t.label }))} />}</Field>
          <Field label="Ville" required>{(id) => <Input id={id} value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />}</Field>
          <Field label="Quartier(s)">{(id) => <Input id={id} value={f.neighborhood} onChange={(e) => setF({ ...f, neighborhood: e.target.value })} />}</Field>
          <Field label="Budget minimum">{(id) => <Input id={id} type="number" min={0} value={f.budget_min} onChange={(e) => setF({ ...f, budget_min: e.target.value })} />}</Field>
          <Field label="Budget maximum">{(id) => <Input id={id} type="number" min={0} value={f.budget_max} onChange={(e) => setF({ ...f, budget_max: e.target.value })} />}</Field>
          <Field label="Surface minimum (m²)">{(id) => <Input id={id} type="number" min={1} value={f.surface_min} onChange={(e) => setF({ ...f, surface_min: e.target.value })} />}</Field>
          <Field label="Chambres minimum">{(id) => <Input id={id} type="number" min={0} value={f.bedrooms_min} onChange={(e) => setF({ ...f, bedrooms_min: e.target.value })} />}</Field>
        </div>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-slate-700">Souhaits</legend>
          <div className="flex flex-wrap gap-3">
            {cat.data?.features.map((ft) => <Checkbox key={ft.code} label={ft.label} checked={features.includes(ft.code)} onChange={(v) => setFeatures(v ? [...features, ft.code] : features.filter((x) => x !== ft.code))} />)}
          </div>
        </fieldset>
        <Field label="Précisions">{(id) => <Textarea id={id} value={f.comments} onChange={(e) => setF({ ...f, comments: e.target.value })} />}</Field>
        <Checkbox label="J'accepte que l'agence conserve et utilise ces informations pour me proposer des biens." checked={consent} onChange={setConsent} />
        <Button type="submit" loading={send.isPending} disabled={!consent || f.full_name.trim().length < 2 || f.phone.trim().length < 6 || f.city.trim().length < 2}>Envoyer ma recherche</Button>
      </form>
    </div>
  );
}
