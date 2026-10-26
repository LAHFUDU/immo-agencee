import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setCsrfToken, setUnauthorizedHandler } from "./api";
import { useQueryClient } from "@tanstack/react-query";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role_name: string;
  role_code: string;
  is_superadmin: boolean;
  must_change_password: boolean;
  language: string;
  permissions: string[];
  csrf_token: string;
}

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  can: (...perms: string[]) => boolean;
  canAny: (...perms: string[]) => boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  setMe: (me: Me | null) => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const setMe = useCallback((m: Me | null) => {
    setCsrfToken(m?.csrf_token ?? null);
    setMeState(m);
  }, []);

  useEffect(() => {
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
    setUnauthorizedHandler(() => {
      setMe(null);
      qc.clear();
    });
  }, [setMe, qc]);

  const value = useMemo<AuthCtx>(() => {
    const perms = new Set(me?.permissions ?? []);
    return {
      me,
      loading,
      can: (...p) => p.every((x) => perms.has(x)),
      canAny: (...p) => p.some((x) => perms.has(x)),
      login: async (email, password) => {
        const m = await api<Me>("/auth/login", { body: { email, password } });
        qc.clear();
        setMe(m);
        return m;
      },
      logout: async () => {
        try {
          await api("/auth/logout", { method: "POST" });
        } finally {
          setMe(null);
          qc.clear();
        }
      },
      setMe,
    };
  }, [me, loading, setMe, qc]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
