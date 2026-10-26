import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Ban, Lock, Plus, ShieldAlert, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable, DealStatusBadge, ExportButtons, FilterPanel, PropertyStatusBadge, ReasonModal, type Column } from "../../components/domain";
import { BackLink } from "../../components/Layout";
import { Alert, Badge, Button, Card, Checkbox, EmptyState, ErrorState, Field, Input, KV, Modal, PageHeader, Pagination, Select, Spinner, Textarea, useToast } from "../../components/ui";
import { api, ApiError, type Page } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { date, dateTime, money } from "../../lib/format";
import { useDirectory, useUrlFilters } from "../../lib/hooks";
import { L, options } from "../../lib/i18n";
import type { Deal } from "../../lib/types";
import { ActivitiesPanel } from "../requests/RequestDetail";

const DEFAULTS = {} as Record<string, string>;

export function DealList() {
  const { can } = useAuth();
  const { values, set, replaceAll, page } = useUrlFilters(DEFAULTS);
  const agents = useDirectory(true);
  const query = useMemo(() => ({ ...values, page: String(page), page_size: "25" }), [values, page]);
  const q = useQuery({ queryKey: ["deals", query], queryFn: () => api<Page<Deal>>("/deals", { query }), placeholderData: (p) => p });
  const activeCount = Object.entries(values).filter(([k, v]) => v && k !== "page").length;
  const columns: Column<Deal>[] = [
    { key: "ref", header: "Transaction", render: (d) => <div><Link to={`/app/deals/${d.id}`} className="font-medium text-brand-800 hover:underline">{d.reference}</Link><p className="text-xs text-slate-500">{L.transaction[d.transaction_type]} · {date(d.created_at)}</p></div> },
    { key: "cust", header: "Client", render: (d) => d.customer_name },
    { key: "prop", header: "Bien", render: (d) => <span>{d.property_reference} <span className="text-slate-500">— {d.property_title}</span></span>, secondary: true },
    { key: "price", header: "Prix", render: (d) => <span className="whitespace-nowrap">{money(d.agreed_price ?? d.asking_price, d.currency)}</span> },
    { key: "status", header: "Statut", render: (d) => <DealStatusBadge s={d.status} /> },
    { key: "agent", header: "Agent", render: (d) => d.agent?.full_name ?? "—", secondary: true },
    ...(can("commissions.view") ? [{ key: "comm", header: "Commission", render: (d: Deal) => money(d.commission_amount, d.currency), secondary: true }] : []),
  ];
  return (
    <>
      <PageHeader title="Ventes & locations" subtitle="Suivi des négociations, offres, réservations et transactions conclues." actions={<ExportButtons path="/deals/export" query={query} perm="reports.export" />} />
      <FilterPanel page="deals" values={values} onApply={replaceAll} activeCount={activeCount}>
        <Field label="Recherche">{(id) => <Input id={id} value={values.q ?? ""} onChange={(e) => set({ q: e.target.value })} placeholder="Réf., client, bien…" />}</Field>
        <Field label="Statut">{(id) => <Select id={id} value={values.status ?? ""} onChange={(e) => set({ status: e.target.value })} placeholder="Tous" options={[{ value: "negotiation,reserved", label: "En cours" }, ...options(L.dealStatus)]} />}</Field>
        <Field label="Type">{(id) => <Select id={id} value={values.transaction_type ?? ""} onChange={(e) => set({ transaction_type: e.target.value })} placeholder="Tous" options={options(L.transaction)} />}</Field>
        {can("deals.view_all") && <Field label="Agent">{(id) => <Select id={id} value={values.agent_id ?? ""} onChange={(e) => set({ agent_id: e.target.value })} placeholder="Tous" options={[{ value: "me", label: "Moi" }, ...(agents.data ?? []).map((a) => ({ value: a.id, label: a.full_name }))]} />}</Field>}
        <Field label="Créée du">{(id) => <Input id={id} type="date" value={values.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} />}</Field>
        <Field label="au">{(id) => <Input id={id} type="date" value={values.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} />}</Field>
      </FilterPanel>
      <Card>
        {q.error ? (
          <ErrorState error={q.error} />
        ) : (
          <>
            <DataTable rows={q.data?.items} columns={columns} loading={q.isFetching} rowHref={(d) => `/app/deals/${d.id}`} empty={<EmptyState title="Aucune transaction">Ouvrez une transaction depuis un bien correspondant dans une demande client.</EmptyState>} />
            {q.data && <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={(p) => set({ page: String(p) }, false)} />}
          </>
        )}
      </Card>
    </>
  );
}

export function DealDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["deal", id], queryFn: () => api<Deal>(`/deals/${id}`) });
  const [offerOpen, setOfferOpen] = useState(false);
  const [winOpen, setWinOpen] = useState(false);
  const [closeMode, setCloseMode] = useState<"lose" | "cancel" | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [commOpen, setCommOpen] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["deal", id] });
    qc.invalidateQueries({ queryKey: ["deals"] });
    qc.invalidateQueries({ queryKey: ["activities", "deal", id] });
  };
  const reserve = useMutation({
    mutationFn: (override: boolean) => api(`/deals/${id}/reserve`, { body: { override } }),
    onSuccess: () => {
      setConflict(null);
      refresh();
      toast.success("Bien réservé pour cette transaction.");
    },
    onError: (e) => (e instanceof ApiError && e.status === 409 ? setConflict(e.message) : toast.error(e)),
  });
  const offerStatus = useMutation({
    mutationFn: (v: { offer: string; status: string }) => api(`/deals/${id}/offers/${v.offer}`, { method: "PATCH", body: { status: v.status } }),
    onSuccess: refresh,
    onError: toast.error,
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data!;
  const active = d.status === "negotiation" || d.status === "reserved";
  const manage = can("deals.manage") && active;

  return (
    <>
      <PageHeader
        back={<BackLink to="/app/deals">Ventes & locations</BackLink>}
        title={<span className="flex flex-wrap items-center gap-2">{d.reference} <DealStatusBadge s={d.status} /></span>}
        subtitle={`${L.transaction[d.transaction_type]} · ouverte le ${date(d.created_at)}`}
        actions={
          manage && (
            <>
              {d.status === "negotiation" && (
                <Button variant="secondary" icon={<Lock className="h-4 w-4" />} loading={reserve.isPending} onClick={() => reserve.mutate(false)}>
                  Réserver le bien
                </Button>
              )}
              <Button icon={<BadgeCheck className="h-4 w-4" />} onClick={() => setWinOpen(true)}>
                Conclure
              </Button>
              <Button variant="secondary" icon={<XCircle className="h-4 w-4" />} onClick={() => setCloseMode("lose")}>
                Perdue
              </Button>
              <Button variant="ghost" icon={<Ban className="h-4 w-4" />} onClick={() => setCloseMode("cancel")}>
                Annuler
              </Button>
            </>
          )
        }
      />
      {conflict && (
        <div className="mb-4">
          <Alert color="red" title="Réservation impossible">
            <p>{conflict}</p>
            {can("deals.override_reservation") && (
              <Button className="mt-2" size="sm" variant="danger" icon={<ShieldAlert className="h-4 w-4" />} loading={reserve.isPending} onClick={() => reserve.mutate(true)}>
                Autoriser une double réservation (administrateur)
              </Button>
            )}
          </Alert>
        </div>
      )}
      {!active && <div className="mb-4"><Alert color={d.status === "won" ? "green" : "blue"}>Transaction clôturée le {dateTime(d.closed_at)} — l'historique est conservé en lecture seule.{d.lost_reason ? ` Motif : ${d.lost_reason}` : ""}</Alert></div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Transaction" className="lg:col-span-2">
          <KV
            items={[
              ["Client", <Link key="c" to={`/app/customers/${d.customer_id}`} className="text-brand-700 hover:underline">{d.customer_name}</Link>],
              ["Bien", <span key="p"><Link to={`/app/properties/${d.property_id}`} className="text-brand-700 hover:underline">{d.property_reference} — {d.property_title}</Link> <PropertyStatusBadge s={d.property_status} /></span>],
              ["Demande", d.request_id ? <Link key="r" to={`/app/requests/${d.request_id}`} className="text-brand-700 hover:underline">voir la demande</Link> : "—"],
              ["Agent", d.agent?.full_name ?? "—"],
              ["Prix demandé", money(d.asking_price, d.currency)],
              ["Prix convenu", money(d.agreed_price, d.currency)],
              ["Clôture prévue", date(d.expected_closing_date)],
              ["Clôture réelle", date(d.actual_closing_date)],
              ["Réservation", d.holds_reservation ? (d.reservation_override ? "Oui (double réservation autorisée)" : "Oui") : "Non"],
              ["Notes", d.notes ?? "—"],
            ]}
          />
        </Card>
        <Card title="Commission" actions={can("commissions.manage") && <Button size="sm" variant="secondary" onClick={() => setCommOpen(true)}>Ajuster</Button>}>
          {d.commission_amount !== null || d.commission_rate !== null ? (
            <KV cols={1} items={[["Taux", d.commission_rate !== null ? `${Number(d.commission_rate)} %` : "—"], ["Montant", money(d.commission_amount, d.currency)], ["Origine", d.commission_overridden ? "Ajustée manuellement" : "Règle de commission"]]} />
          ) : (
            <p className="text-sm text-slate-500">{can("commissions.view") || d.agent ? "Aucune règle de commission applicable." : "Non visible."}</p>
          )}
        </Card>
      </div>
      <Card title="Offres et négociation" className="mt-4" actions={manage && <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setOfferOpen(true)}>Nouvelle offre</Button>}>
        {!d.offers.length ? (
          <EmptyState title="Aucune offre enregistrée" />
        ) : (
          <ul className="divide-y divide-slate-100">
            {d.offers.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                <span className="w-32 text-slate-500">{dateTime(o.offered_at)}</span>
                <Badge color={o.party === "customer" ? "blue" : "violet"}>{L.offerParty[o.party]}</Badge>
                <span className="font-semibold">{money(o.amount, d.currency)}</span>
                <span className="flex-1 text-slate-500">{o.notes}</span>
                {manage && o.status === "pending" ? (
                  <Select aria-label="Statut de l'offre" className="max-w-[160px]" value={o.status} onChange={(e) => offerStatus.mutate({ offer: o.id, status: e.target.value })} options={options(L.offerStatus)} />
                ) : (
                  <Badge color={o.status === "accepted" ? "green" : o.status === "rejected" ? "red" : "gray"}>{L.offerStatus[o.status]}</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <div className="mt-4">
        <ActivitiesPanel scope="deal" id={d.id} canAdd={false} />
      </div>
      {offerOpen && <OfferModal deal={d} onClose={() => setOfferOpen(false)} onDone={refresh} />}
      {winOpen && <WinModal deal={d} onClose={() => setWinOpen(false)} onDone={refresh} />}
      {commOpen && <CommissionModal deal={d} onClose={() => setCommOpen(false)} onDone={refresh} />}
      <ReasonModal
        open={!!closeMode}
        onClose={() => setCloseMode(null)}
        title={closeMode === "lose" ? "Transaction perdue" : "Annuler la transaction"}
        label="Motif (utilisé dans les rapports d'échec)"
        onSubmit={async (reason) => {
          await api(`/deals/${d.id}/${closeMode}`, { body: { reason } });
          refresh();
          toast.success("Transaction clôturée. Le bien est remis sur le marché si plus aucune négociation n'est en cours.");
        }}
      />
    </>
  );
}

function OfferModal({ deal, onClose, onDone }: { deal: Deal; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const [party, setParty] = useState("customer");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => api(`/deals/${deal.id}/offers`, { body: { amount, party, notes: notes || null } }),
    onSuccess: () => {
      onDone();
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal open onClose={onClose} title="Nouvelle offre" footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} disabled={!amount} onClick={() => save.mutate()}>Enregistrer</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={`Montant (${deal.currency})`} required>{(id) => <Input id={id} type="number" min={0} value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
        <Field label="Émise par">{(id) => <Select id={id} value={party} onChange={(e) => setParty(e.target.value)} options={options(L.offerParty)} />}</Field>
      </div>
      <Field label="Notes" className="mt-3">{(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
    </Modal>
  );
}

function WinModal({ deal, onClose, onDone }: { deal: Deal; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [price, setPrice] = useState(deal.agreed_price ?? deal.asking_price ?? "");
  const [closing, setClosing] = useState(new Date().toISOString().slice(0, 10));
  const save = useMutation({
    mutationFn: () => api(`/deals/${deal.id}/win`, { body: { agreed_price: price, closing_date: closing } }),
    onSuccess: () => {
      onDone();
      toast.success(`Transaction conclue : le bien est désormais ${deal.transaction_type === "sale" ? "vendu" : "loué"} et retiré des correspondances.`);
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal open onClose={onClose} title="Conclure la transaction" footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} disabled={!price} onClick={() => save.mutate()}>Confirmer</Button></>}>
      <p className="mb-3 text-sm text-slate-600">Le bien passera au statut « {deal.transaction_type === "sale" ? "Vendu" : "Loué"} », la demande sera marquée « Convertie » et les autres négociations sur ce bien seront clôturées.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={`Prix convenu (${deal.currency})`} required>{(id) => <Input id={id} type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} />}</Field>
        <Field label="Date de clôture">{(id) => <Input id={id} type="date" value={closing} onChange={(e) => setClosing(e.target.value)} />}</Field>
      </div>
    </Modal>
  );
}

function CommissionModal({ deal, onClose, onDone }: { deal: Deal; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [rate, setRate] = useState(deal.commission_rate ?? "");
  const [amount, setAmount] = useState(deal.commission_amount ?? "");
  const [reset, setReset] = useState(false);
  const save = useMutation({
    mutationFn: () => api(`/deals/${deal.id}/commission`, { body: reset ? { reset: true } : { commission_rate: rate || null, commission_amount: amount || null } }),
    onSuccess: () => {
      onDone();
      onClose();
    },
    onError: toast.error,
  });
  return (
    <Modal open onClose={onClose} title="Ajuster la commission" footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Enregistrer</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Taux (%)">{(id) => <Input id={id} type="number" min={0} max={100} step="0.001" value={rate} disabled={reset} onChange={(e) => setRate(e.target.value)} />}</Field>
        <Field label={`Montant (${deal.currency})`} hint="Laisser vide pour calculer depuis le taux.">{(id) => <Input id={id} type="number" min={0} value={amount} disabled={reset} onChange={(e) => setAmount(e.target.value)} />}</Field>
      </div>
      <div className="mt-3">
        <Checkbox label="Revenir au calcul automatique (règles de commission)" checked={reset} onChange={setReset} />
      </div>
    </Modal>
  );
}
