"""Permission catalogue and default role profiles.

Permissions are enforced server side in every endpoint (see app.core.deps.require).
"*_all" permissions widen the data scope; without them a user only sees records
assigned to / created by them (plus unassigned new requests, so agents can pick them up).
"""

PERMISSIONS: dict[str, tuple[str, str]] = {
    # code: (module, French label)
    "dashboard.view": ("dashboard", "Voir le tableau de bord"),
    "requests.view": ("requests", "Voir les demandes (les siennes et les nouvelles non assignées)"),
    "requests.view_all": ("requests", "Voir toutes les demandes"),
    "requests.create": ("requests", "Créer des demandes"),
    "requests.edit": ("requests", "Modifier les demandes"),
    "requests.archive": ("requests", "Archiver / clôturer les demandes"),
    "requests.assign": ("requests", "Assigner les demandes aux agents"),
    "requests.export": ("requests", "Exporter les demandes"),
    "customers.view": ("customers", "Voir les clients (les siens)"),
    "customers.view_all": ("customers", "Voir tous les clients"),
    "customers.create": ("customers", "Créer des clients"),
    "customers.edit": ("customers", "Modifier les clients"),
    "customers.archive": ("customers", "Archiver les clients"),
    "customers.export": ("customers", "Exporter les clients"),
    "properties.view": ("properties", "Voir les biens"),
    "properties.create": ("properties", "Créer des biens"),
    "properties.edit": ("properties", "Modifier les biens et leur statut"),
    "properties.archive": ("properties", "Archiver les biens"),
    "properties.import": ("properties", "Importer des biens (CSV / Excel)"),
    "properties.export": ("properties", "Exporter les biens"),
    "properties.publish": ("properties", "Publier les biens sur le site public"),
    "properties.view_confidential": ("properties", "Voir adresse, propriétaire, notes internes et documents"),
    "matches.view": ("matches", "Voir les correspondances"),
    "matches.manage": ("matches", "Proposer / rejeter des correspondances"),
    "visits.view": ("visits", "Voir les visites et rendez-vous (les siens)"),
    "visits.view_all": ("visits", "Voir toutes les visites"),
    "visits.manage": ("visits", "Planifier et mettre à jour les visites"),
    "deals.view": ("deals", "Voir les transactions (les siennes)"),
    "deals.view_all": ("deals", "Voir toutes les transactions"),
    "deals.manage": ("deals", "Créer et faire avancer les transactions"),
    "deals.override_reservation": ("deals", "Autoriser une double réservation d'un bien"),
    "commissions.view": ("deals", "Voir les commissions et le chiffre d'affaires"),
    "commissions.manage": ("deals", "Modifier les règles et montants de commission"),
    "reports.view": ("reports", "Voir les rapports"),
    "reports.export": ("reports", "Exporter les rapports"),
    "agents.view": ("agents", "Voir les agents et leurs performances"),
    "users.manage": ("admin", "Gérer les comptes employés"),
    "roles.manage": ("admin", "Gérer les rôles et permissions"),
    "settings.manage": ("admin", "Configurer le système"),
    "audit.view": ("admin", "Consulter le journal d'audit"),
}

ALL_PERMISSION_CODES = list(PERMISSIONS)

_COMMERCIAL = [
    "dashboard.view",
    "requests.view",
    "requests.create",
    "requests.edit",
    "customers.view",
    "customers.create",
    "customers.edit",
    "properties.view",
    "matches.view",
    "matches.manage",
    "visits.view",
    "visits.manage",
    "deals.view",
    "deals.manage",
]

DEFAULT_ROLES: dict[str, dict] = {
    "super_admin": {
        "name": "Super administrateur",
        "description": "Accès complet à toute la plateforme.",
        "is_superadmin": True,
        "permissions": ALL_PERMISSION_CODES,
    },
    "commercial_agent": {
        "name": "Agent commercial",
        "description": "Accès commercial restreint : ses demandes, ses clients, l'inventaire et les correspondances.",
        "is_superadmin": False,
        "permissions": _COMMERCIAL,
    },
    "sales_manager": {
        "name": "Responsable commercial",
        "description": "Supervise les agents, assigne les demandes et suit les transactions.",
        "is_superadmin": False,
        "permissions": _COMMERCIAL
        + [
            "requests.view_all",
            "requests.archive",
            "requests.assign",
            "requests.export",
            "customers.view_all",
            "customers.archive",
            "customers.export",
            "visits.view_all",
            "deals.view_all",
            "commissions.view",
            "reports.view",
            "reports.export",
            "agents.view",
            "properties.view_confidential",
        ],
    },
    "property_manager": {
        "name": "Gestionnaire de biens",
        "description": "Gère l'inventaire des biens, les propriétaires, les photos et les imports.",
        "is_superadmin": False,
        "permissions": [
            "dashboard.view",
            "properties.view",
            "properties.create",
            "properties.edit",
            "properties.archive",
            "properties.import",
            "properties.export",
            "properties.publish",
            "properties.view_confidential",
            "matches.view",
        ],
    },
}
