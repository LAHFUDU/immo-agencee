import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Catalog, UserRef } from "./types";

export function useCatalog() {
  const { me } = useAuth();
  const q = useQuery({ queryKey: ["catalog"], queryFn: () => api<Catalog>("/catalog"), staleTime: 5 * 60_000, enabled: !!me });
  const typeLabel = useCallback(
    (code: string) => q.data?.property_types.find((t) => t.code === code)?.label ?? code,
    [q.data],
  );
  const featureLabel = useCallback((code: string) => q.data?.features.find((f) => f.code === code)?.label ?? code, [q.data]);
  return { ...q, typeLabel, featureLabel };
}

export function useDirectory(agentsOnly = false) {
  const { me } = useAuth();
  return useQuery({
    queryKey: ["directory", agentsOnly],
    queryFn: () => api<UserRef[]>("/users/directory", { query: { agents_only: agentsOnly } }),
    staleTime: 5 * 60_000,
    enabled: !!me,
  });
}

/** Filter state kept in the URL so lists are shareable and survive navigation. */
export function useUrlFilters<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams();
  const values = useMemo(() => {
    const out: Record<string, string> = { ...defaults };
    params.forEach((v, k) => {
      out[k] = v;
    });
    return out as T & { page?: string };
  }, [params, defaults]);

  const set = useCallback(
    (patch: Partial<Record<string, string>>, resetPage = true) => {
      const next = new URLSearchParams(params);
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === "" || v === null) next.delete(k);
        else next.set(k, v);
      }
      if (resetPage && !("page" in patch)) next.delete("page");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const replaceAll = useCallback(
    (all: Record<string, string>) => {
      const next = new URLSearchParams();
      for (const [k, v] of Object.entries(all)) if (v) next.set(k, v);
      setParams(next, { replace: true });
    },
    [setParams],
  );

  return { values, set, replaceAll, page: Number(params.get("page") ?? 1) };
}
