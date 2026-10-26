/**
 * Minimal i18n layer. French is the default and the only complete locale today; the structure
 * (keyed messages + per-locale text direction) is ready for Arabic (RTL) and English.
 */

export type Locale = "fr" | "en" | "ar";

const fr = {
  "nav.dashboard": "Tableau de bord",
  "nav.requests": "Demandes clients",
  "nav.waiting": "Liste d'attente",
  "nav.properties": "Biens",
  "nav.matching": "Correspondances",
  "nav.customers": "Clients",
  "nav.visits": "Visites & rendez-vous",
  "nav.deals": "Ventes & locations",
  "nav.agents": "Agents commerciaux",
  "nav.notifications": "Notifications",
  "nav.reports": "Rapports",
  "nav.users": "Utilisateurs",
  "nav.settings": "Paramètres",
  "nav.audit": "Journal d'audit",
  "common.save": "Enregistrer",
  "common.cancel": "Annuler",
  "common.confirm": "Confirmer",
  "common.edit": "Modifier",
  "common.create": "Créer",
  "common.search": "Rechercher",
  "common.loading": "Chargement…",
  "common.none": "Aucun résultat",
  "common.export": "Exporter",
  "common.filters": "Filtres",
  "common.reset": "Réinitialiser",
  "common.logout": "Se déconnecter",
};

type Messages = typeof fr;
const messages: Record<Locale, Partial<Messages>> = { fr, en: {}, ar: {} };
let current: Locale = "fr";

export function setLocale(l: Locale) {
  current = l;
  document.documentElement.lang = l;
  document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
}

export function t(key: keyof Messages): string {
  return messages[current][key] ?? fr[key] ?? key;
}

// ---------------------------------------------------------------- enum labels

export const L = {
  transaction: { sale: "Vente", rent: "Location" } as Record<string, string>,
  transactionWish: { sale: "Achat", rent: "Location" } as Record<string, string>,
  requestStatus: {
    new: "Nouvelle demande",
    to_contact: "À contacter",
    contacted: "Contacté",
    proposed: "Biens proposés",
    visit_scheduled: "Visite planifiée",
    negotiation: "Négociation",
    converted: "Convertie avec succès",
    closed_lost: "Clôturée sans succès",
    archived: "Archivée",
  } as Record<string, string>,
  propertyStatus: {
    available: "Disponible",
    reserved: "Réservé",
    under_negotiation: "En négociation",
    sold: "Vendu",
    rented: "Loué",
    unavailable: "Indisponible",
    archived: "Archivé",
  } as Record<string, string>,
  priority: { low: "Basse", normal: "Normale", high: "Haute", urgent: "Urgente" } as Record<string, string>,
  matchCategory: { exact: "Exacte", strong: "Forte", partial: "Partielle", ineligible: "Non conforme" } as Record<string, string>,
  matchStatus: {
    suggested: "Suggéré",
    proposed: "Proposé",
    interested: "Intéressé",
    visit_scheduled: "Visite planifiée",
    rejected: "Rejeté",
  } as Record<string, string>,
  dealStatus: { negotiation: "Négociation", reserved: "Réservé", won: "Conclue", lost: "Perdue", cancelled: "Annulée" } as Record<string, string>,
  visitStatus: { scheduled: "Planifiée", done: "Effectuée", cancelled: "Annulée", no_show: "Client absent" } as Record<string, string>,
  taskStatus: { open: "À faire", done: "Terminée", cancelled: "Annulée" } as Record<string, string>,
  activityType: {
    call: "Appel",
    meeting: "Rendez-vous",
    email: "E-mail",
    whatsapp: "WhatsApp",
    sms: "SMS",
    visit: "Visite",
    offer: "Offre",
    note: "Note",
    web_contact: "Site web",
    status_change: "Changement de statut",
  } as Record<string, string>,
  contactMethod: { phone: "Téléphone", email: "E-mail", whatsapp: "WhatsApp", sms: "SMS", any: "Indifférent" } as Record<string, string>,
  source: {
    website: "Site web",
    referral: "Recommandation",
    phone: "Appel téléphonique",
    walk_in: "Visite en agence",
    social_media: "Réseaux sociaux",
    portal: "Portail immobilier",
    other: "Autre",
  } as Record<string, string>,
  offerParty: { customer: "Client", owner: "Propriétaire" } as Record<string, string>,
  offerStatus: { pending: "En attente", accepted: "Acceptée", rejected: "Refusée", countered: "Contre-offre", withdrawn: "Retirée" } as Record<string, string>,
};

export const options = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }));
