/** Thin fetch wrapper: same-origin cookies, CSRF header on writes, consistent errors. */

let csrfToken: string | null = null;
export const setCsrfToken = (t: string | null) => {
  csrfToken = t;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;
  errors?: { field: string; message: string }[];
  constructor(status: number, message: string, detail: unknown, errors?: { field: string; message: string }[]) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.errors = errors;
  }
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

export function qs(query?: Query): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length) p.set(k, v.join(","));
    } else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; query?: Query; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}${qs(opts.query)}`, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch {
    throw new ApiError(0, "Impossible de joindre le serveur. Vérifiez votre connexion.", null);
  }
  if (res.status === 204) return undefined as T;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !path.startsWith("/auth/")) onUnauthorized();
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? (res.status === 403 ? "Accès refusé." : res.status === 404 ? "Élément introuvable." : `Erreur ${res.status}`);
    throw new ApiError(res.status, message, detail, data?.errors);
  }
  return data as T;
}

/** Downloads a file produced by an authenticated GET endpoint (exports, documents). */
export async function download(path: string, query?: Query, fallbackName = "export") {
  const res = await fetch(`/api${path}${qs(query)}`, { credentials: "same-origin" });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, data?.detail ?? "Téléchargement impossible.", data);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
