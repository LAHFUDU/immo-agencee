import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, KeyRound } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Field, Input, KV, PageHeader, Spinner, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth, type Me } from "../lib/auth";

function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-950 via-brand-900 to-brand-700 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-white">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gold-500 text-brand-950">
            <Building2 className="h-5 w-5" />
          </span>
          <span className="text-xl font-semibold tracking-tight">Immo Agence</span>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-2xl">
          <h1 className="mb-4 text-lg font-semibold text-slate-900">{title}</h1>
          {children}
        </div>
        <p className="mt-6 text-center text-xs text-brand-200">Espace privé réservé au personnel de l'agence.</p>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { me, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app";
  if (me) return <Navigate to={me.must_change_password ? "/app/account" : from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const m = await login(email.trim(), password);
      navigate(m.must_change_password ? "/app/account" : from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Connexion">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Alert color="red">{error}</Alert>}
        <Field label="Adresse e-mail" required>
          {(id) => <Input id={id} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />}
        </Field>
        <Field label="Mot de passe" required>
          {(id) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
        </Field>
        <Button type="submit" className="w-full" loading={busy} disabled={!email || !password}>
          Se connecter
        </Button>
        <p className="text-center text-xs text-slate-500">Mot de passe oublié ? Demandez un lien de réinitialisation à votre administrateur.</p>
      </form>
    </AuthShell>
  );
}

const PWD_HINT = "10 caractères minimum, avec au moins 3 types parmi : minuscules, majuscules, chiffres, symboles.";

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { setMe } = useAuth();
  const navigate = useNavigate();
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const info = useQuery({
    queryKey: ["token-info", token],
    queryFn: () => api<{ email: string; full_name: string; purpose: string }>("/auth/token-info", { query: { token } }),
    retry: false,
    enabled: !!token,
  });
  const submit = useMutation({
    mutationFn: () => api<Me>("/auth/accept-token", { body: { token, new_password: pwd } }),
    onSuccess: (m) => {
      setMe(m);
      navigate("/app", { replace: true });
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Erreur"),
  });
  if (!token || info.isError)
    return (
      <AuthShell title="Lien invalide">
        <Alert color="red">Ce lien est invalide ou a expiré. Demandez un nouveau lien à votre administrateur.</Alert>
        <Link to="/login" className="mt-4 block text-center text-sm text-brand-700 hover:underline">
          Retour à la connexion
        </Link>
      </AuthShell>
    );
  if (info.isLoading) return <Spinner />;
  return (
    <AuthShell title={info.data?.purpose === "invite" ? "Bienvenue ! Choisissez votre mot de passe" : "Nouveau mot de passe"}>
      <p className="mb-4 text-sm text-slate-600">
        {info.data?.full_name} — <span className="font-medium">{info.data?.email}</span>
      </p>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (pwd !== pwd2) return setError("Les mots de passe ne correspondent pas.");
          submit.mutate();
        }}
      >
        {error && <Alert color="red">{error}</Alert>}
        <Field label="Nouveau mot de passe" hint={PWD_HINT} required>
          {(id) => <Input id={id} type="password" autoComplete="new-password" value={pwd} onChange={(e) => setPwd(e.target.value)} />}
        </Field>
        <Field label="Confirmation" required>
          {(id) => <Input id={id} type="password" autoComplete="new-password" value={pwd2} onChange={(e) => setPwd2(e.target.value)} />}
        </Field>
        <Button type="submit" className="w-full" loading={submit.isPending} disabled={!pwd || !pwd2}>
          Valider
        </Button>
      </form>
    </AuthShell>
  );
}

export function AccountPage() {
  const { me, setMe } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [pwd, setPwd] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: () => api<Me>("/auth/change-password", { body: { current_password: cur, new_password: pwd } }),
    onSuccess: (m) => {
      setMe(m);
      setCur("");
      setPwd("");
      setPwd2("");
      toast.success("Mot de passe modifié. Vos autres sessions ont été déconnectées.");
    },
    onError: (e) => setError(e instanceof Error ? e.message : "Erreur"),
  });
  if (!me) return null;
  return (
    <>
      <PageHeader title="Mon compte" />
      {me.must_change_password && (
        <div className="mb-4">
          <Alert color="amber" title="Changement de mot de passe requis">
            Vous utilisez un mot de passe temporaire. Choisissez un nouveau mot de passe pour accéder à l'application.
          </Alert>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profil">
          <KV items={[["Nom", me.full_name], ["E-mail", me.email], ["Rôle", me.role_name], ["Permissions", `${me.permissions.length} permission(s)`]]} />
        </Card>
        <Card title={<span className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Changer de mot de passe</span>}>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              if (pwd !== pwd2) return setError("Les mots de passe ne correspondent pas.");
              change.mutate();
            }}
          >
            {error && <Alert color="red">{error}</Alert>}
            <Field label="Mot de passe actuel" required>
              {(id) => <Input id={id} type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />}
            </Field>
            <Field label="Nouveau mot de passe" hint={PWD_HINT} required>
              {(id) => <Input id={id} type="password" autoComplete="new-password" value={pwd} onChange={(e) => setPwd(e.target.value)} />}
            </Field>
            <Field label="Confirmation" required>
              {(id) => <Input id={id} type="password" autoComplete="new-password" value={pwd2} onChange={(e) => setPwd2(e.target.value)} />}
            </Field>
            <Button type="submit" loading={change.isPending} disabled={!cur || !pwd}>
              Mettre à jour
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
