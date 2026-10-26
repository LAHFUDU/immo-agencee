import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Pencil, Plus, ShieldCheck, Trash2, UserCheck, UserX } from "lucide-react";
import { useState } from "react";
import { DataTable, type Column } from "../../components/domain";
import { Alert, Badge, Button, Card, Checkbox, ConfirmButton, ErrorState, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, Textarea, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { relative } from "../../lib/format";
import type { Role, UserAccount } from "../../lib/types";

interface CredentialResult {
  user: UserAccount;
  mode: "invite" | "temp_password";
  invite_url: string | null;
  temp_password: string | null;
  email_status: string;
}

export default function UsersPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"users" | "roles">("users");
  return (
    <>
      <PageHeader title="Utilisateurs & accès" subtitle="Comptes employés, rôles et permissions. Les permissions sont vérifiées côté serveur pour chaque requête." />
      {can("roles.manage") && <Tabs value={tab} onChange={setTab} tabs={[{ value: "users", label: "Comptes" }, { value: "roles", label: "Rôles & permissions" }]} />}
      {tab === "users" ? <UsersTab /> : <RolesTab />}
    </>
  );
}

function CredentialBox({ result, onClose }: { result: CredentialResult; onClose: () => void }) {
  const toast = useToast();
  const value = result.invite_url ?? result.temp_password ?? "";
  return (
    <Modal open onClose={onClose} title="Identifiants à transmettre" footer={<Button onClick={onClose}>J'ai transmis les identifiants</Button>}>
      <Alert color="amber" title="Affiché une seule fois">
        {result.mode === "invite"
          ? "Lien d'invitation personnel (valable 72 h, usage unique). L'employé choisira lui-même son mot de passe."
          : "Mot de passe temporaire : l'employé devra le changer à sa première connexion."}
        {result.email_status === "sent" && " Un e-mail a également été envoyé."}
        {result.email_status === "not_configured" && " Aucun e-mail n'a été envoyé (SMTP non configuré) : transmettez-le par un canal sûr."}
        {result.email_status === "failed" && " L'envoi de l'e-mail a échoué : transmettez-le par un canal sûr."}
      </Alert>
      <div className="mt-3 flex items-center gap-2">
        <Input readOnly value={value} aria-label="Identifiant" className="font-mono text-xs" onFocus={(e) => e.target.select()} />
        <Button
          variant="secondary"
          icon={<Copy className="h-4 w-4" />}
          onClick={() => navigator.clipboard.writeText(value).then(() => toast.success("Copié."), () => toast.error("Copie impossible."))}
        >
          Copier
        </Button>
      </div>
      <p className="mt-2 text-xs text-slate-500">Compte : {result.user.email}</p>
    </Modal>
  );
}

function UsersTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<UserAccount[]>("/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  const [editing, setEditing] = useState<UserAccount | "new" | null>(null);
  const [cred, setCred] = useState<CredentialResult | null>(null);
  const [resetFor, setResetFor] = useState<UserAccount | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const toggle = useMutation({
    mutationFn: (u: UserAccount) => api(`/users/${u.id}/${u.is_active ? "deactivate" : "reactivate"}`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      toast.success("Compte mis à jour.");
    },
    onError: toast.error,
  });
  const columns: Column<UserAccount>[] = [
    { key: "name", header: "Employé", render: (u) => <div><p className="font-medium text-slate-900">{u.full_name}</p><p className="text-xs text-slate-500">{u.email}</p></div> },
    { key: "role", header: "Rôle", render: (u) => <div className="flex flex-wrap gap-1"><Badge color={u.role_code === "super_admin" ? "violet" : "teal"}>{u.role_name}</Badge>{u.is_agent && <Badge>Agent</Badge>}</div> },
    { key: "state", header: "État", render: (u) => (u.is_active ? (u.must_change_password ? <Badge color="amber">Mot de passe à changer</Badge> : <Badge color="green">Actif</Badge>) : <Badge color="red">Désactivé</Badge>) },
    { key: "login", header: "Dernière connexion", render: (u) => <span className="text-slate-500">{u.last_login_at ? relative(u.last_login_at) : "Jamais"}</span>, secondary: true },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (u) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(u)} aria-label="Modifier" />
          <Button size="sm" variant="ghost" icon={<KeyRound className="h-3.5 w-3.5" />} onClick={() => setResetFor(u)} aria-label="Réinitialiser le mot de passe" />
          {u.id !== me?.id && (
            <ConfirmButton
              size="sm"
              variant="ghost"
              danger={u.is_active}
              icon={u.is_active ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
              title={u.is_active ? "Désactiver le compte" : "Réactiver le compte"}
              message={u.is_active ? `${u.full_name} sera immédiatement déconnecté et ne pourra plus se connecter. Ses données et son historique sont conservés.` : `${u.full_name} pourra de nouveau se connecter.`}
              onConfirm={() => toggle.mutateAsync(u)}
            >
              {""}
            </ConfirmButton>
          )}
        </div>
      ),
    },
  ];
  return (
    <Card title={`${users.data?.length ?? 0} compte(s)`} actions={<Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>Nouvel employé</Button>}>
      {users.error ? <ErrorState error={users.error} /> : <DataTable rows={users.data} columns={columns} loading={users.isLoading} />}
      {editing && roles.data && (
        <UserModal
          user={editing === "new" ? null : editing}
          roles={roles.data}
          onClose={() => setEditing(null)}
          onCreated={(r) => setCred(r)}
          onSaved={refresh}
        />
      )}
      {resetFor && (
        <ResetModal
          user={resetFor}
          onClose={() => setResetFor(null)}
          onDone={(r) => {
            setResetFor(null);
            setCred(r);
            refresh();
          }}
        />
      )}
      {cred && <CredentialBox result={cred} onClose={() => setCred(null)} />}
    </Card>
  );
}

function UserModal({ user, roles, onClose, onCreated, onSaved }: { user: UserAccount | null; roles: Role[]; onClose: () => void; onCreated: (r: CredentialResult) => void; onSaved: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({
    email: user?.email ?? "", full_name: user?.full_name ?? "", phone: user?.phone ?? "", job_title: user?.job_title ?? "",
    role_id: user?.role_id ?? roles.find((r) => r.code === "commercial_agent")?.id ?? roles[0]?.id ?? "", is_agent: user?.is_agent ?? true,
    credential_mode: "invite" as "invite" | "temp_password",
  });
  const save = useMutation({
    mutationFn: () =>
      user
        ? api(`/users/${user.id}`, { method: "PATCH", body: { email: f.email, full_name: f.full_name, phone: f.phone || null, job_title: f.job_title || null, role_id: f.role_id, is_agent: f.is_agent } })
        : api<CredentialResult>("/users", { body: { ...f, phone: f.phone || null, job_title: f.job_title || null } }),
    onSuccess: (r) => {
      onSaved();
      onClose();
      if (!user) onCreated(r as CredentialResult);
      else toast.success("Compte mis à jour.");
    },
    onError: toast.error,
  });
  return (
    <Modal open onClose={onClose} title={user ? "Modifier le compte" : "Nouvel employé"} footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} disabled={!f.email || f.full_name.length < 2} onClick={() => save.mutate()}>{user ? "Enregistrer" : "Créer le compte"}</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nom complet" required>{(id) => <Input id={id} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />}</Field>
        <Field label="E-mail (identifiant)" required>{(id) => <Input id={id} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
        <Field label="Téléphone">{(id) => <Input id={id} value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
        <Field label="Fonction">{(id) => <Input id={id} value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} />}</Field>
        <Field label="Rôle" required hint="Le rôle détermine les permissions (accès complet ou restreint).">{(id) => <Select id={id} value={f.role_id} onChange={(e) => setF({ ...f, role_id: e.target.value })} options={roles.map((r) => ({ value: r.id, label: r.name }))} />}</Field>
        <div className="flex items-end pb-2"><Checkbox label="Agent commercial (peut recevoir des demandes)" checked={f.is_agent} onChange={(v) => setF({ ...f, is_agent: v })} /></div>
      </div>
      {!user && (
        <fieldset className="mt-4">
          <legend className="mb-2 text-sm font-medium text-slate-700">Identifiants de connexion</legend>
          <div className="space-y-2 text-sm">
            <label className="flex items-start gap-2"><input type="radio" name="mode" checked={f.credential_mode === "invite"} onChange={() => setF({ ...f, credential_mode: "invite" })} className="mt-1" /> <span><strong>Lien d'invitation sécurisé</strong> (recommandé) — l'employé définit son propre mot de passe.</span></label>
            <label className="flex items-start gap-2"><input type="radio" name="mode" checked={f.credential_mode === "temp_password"} onChange={() => setF({ ...f, credential_mode: "temp_password" })} className="mt-1" /> <span><strong>Mot de passe temporaire</strong> — à changer obligatoirement à la première connexion.</span></label>
          </div>
        </fieldset>
      )}
    </Modal>
  );
}

function ResetModal({ user, onClose, onDone }: { user: UserAccount; onClose: () => void; onDone: (r: CredentialResult) => void }) {
  const toast = useToast();
  const [mode, setMode] = useState<"invite" | "temp_password">("invite");
  const save = useMutation({ mutationFn: () => api<CredentialResult>(`/users/${user.id}/reset-password`, { body: { credential_mode: mode } }), onSuccess: onDone, onError: toast.error });
  return (
    <Modal open onClose={onClose} title={`Réinitialiser l'accès de ${user.full_name}`} footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Réinitialiser</Button></>}>
      <p className="mb-3 text-sm text-slate-600">Toutes les sessions ouvertes de cet utilisateur seront fermées.</p>
      <Select aria-label="Méthode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} options={[{ value: "invite", label: "Lien de réinitialisation" }, { value: "temp_password", label: "Mot de passe temporaire" }]} />
    </Modal>
  );
}

// ---------------------------------------------------------------- roles

interface Perm {
  code: string;
  module: string;
  label: string;
}
const MODULES: Record<string, string> = { dashboard: "Tableau de bord", requests: "Demandes", customers: "Clients", properties: "Biens", matches: "Correspondances", visits: "Visites", deals: "Transactions & commissions", reports: "Rapports", agents: "Agents", admin: "Administration" };

function RolesTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Perm[]>("/permissions") });
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const del = useMutation({ mutationFn: (id: string) => api(`/roles/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }), onError: toast.error });
  if (roles.isLoading || perms.isLoading) return <Spinner />;
  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
          Nouveau rôle
        </Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {roles.data?.map((r) => (
          <Card
            key={r.id}
            title={<span className="flex items-center gap-2">{r.is_superadmin && <ShieldCheck className="h-4 w-4 text-violet-600" />}{r.name}{r.is_system && <Badge>système</Badge>}</span>}
            actions={
              !r.is_superadmin && (
                <>
                  <Button size="sm" variant="secondary" onClick={() => setEditing(r)}>Permissions</Button>
                  {!r.is_system && (
                    <ConfirmButton size="sm" variant="ghost" danger icon={<Trash2 className="h-3.5 w-3.5" />} title="Supprimer le rôle" message={`Supprimer le rôle « ${r.name} » ? (impossible s'il est attribué)`} confirmLabel="Supprimer" onConfirm={() => del.mutateAsync(r.id)}>{""}</ConfirmButton>
                  )}
                </>
              )
            }
          >
            <p className="text-sm text-slate-600">{r.description}</p>
            <p className="mt-2 text-xs text-slate-500">{r.is_superadmin ? "Toutes les permissions" : `${r.permissions.length} permission(s)`}</p>
          </Card>
        ))}
      </div>
      {editing && perms.data && <RoleModal role={editing === "new" ? null : editing} perms={perms.data} onClose={() => setEditing(null)} />}
    </>
  );
}

function RoleModal({ role, perms, onClose }: { role: Role | null; perms: Perm[]; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [sel, setSel] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const save = useMutation({
    mutationFn: () => (role ? api(`/roles/${role.id}`, { method: "PUT", body: { name, description, permissions: [...sel] } }) : api("/roles", { body: { name, description, permissions: [...sel] } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roles"] });
      toast.success("Rôle enregistré. Les droits s'appliquent immédiatement.");
      onClose();
    },
    onError: toast.error,
  });
  const byModule = perms.reduce<Record<string, Perm[]>>((acc, p) => ((acc[p.module] ??= []).push(p), acc), {});
  return (
    <Modal open wide onClose={onClose} title={role ? `Rôle : ${role.name}` : "Nouveau rôle"} footer={<><Button variant="secondary" onClick={onClose}>Annuler</Button><Button loading={save.isPending} disabled={name.trim().length < 2} onClick={() => save.mutate()}>Enregistrer</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Nom" required>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        <Field label="Description">{(id) => <Textarea id={id} rows={1} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
      </div>
      <div className="mt-4 space-y-4">
        {Object.entries(byModule).map(([mod, list]) => (
          <fieldset key={mod} className="rounded-lg border border-slate-200 p-3">
            <legend className="px-1 text-sm font-semibold text-slate-700">{MODULES[mod] ?? mod}</legend>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {list.map((p) => (
                <Checkbox
                  key={p.code}
                  label={<span>{p.label} <span className="font-mono text-[10px] text-slate-400">{p.code}</span></span>}
                  checked={sel.has(p.code)}
                  onChange={(v) => {
                    const next = new Set(sel);
                    if (v) next.add(p.code);
                    else next.delete(p.code);
                    setSel(next);
                  }}
                />
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </Modal>
  );
}
