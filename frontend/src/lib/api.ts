```typescript
/** Thin fetch wrapper: API calls, cookies, CSRF header, and consistent errors. */

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

let csrfToken: string | null = null;

export const setCsrfToken = (t: string | null) => {
  csrfToken = t;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;
  errors?: { field: string; message: string }[];

  constructor(
    status: number,
    message: string,
    detail: unknown,
    errors?: { field: string; message: string }[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.errors = errors;
  }
}

type Query = Record<
  string,
  string | number | boolean | null | undefined | string[]
>;

export function qs(query?: Query): string {
  if (!query) return "";

  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;

    if (Array.isArray(value)) {
      if (value.length > 0) {
        params.set(key, value.join(","));
      }
    } else {
      params.set(key, String(value));
    }
  }

  const result = params.toString();
  return result ? `?${result}` : "";
}

let onUnauthorized: (() => void) | null = null;

export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

export async function api<T = unknown>(
  path: string,
  opts: {
    method?: string;
    body?: unknown;
    query?: Query;
    form?: FormData;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const method =
    opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");

  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (method !== "GET" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  let body: BodyInit | undefined;

  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE}/api${path}${qs(opts.query)}`, {
      method,
      headers,
      body,
      credentials: "include",
      signal: opts.signal,
    });
  } catch {
    throw new ApiError(
      0,
      "Impossible de joindre le serveur. Vérifiez votre connexion.",
      null,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");

  const data = isJson
    ? await response.json().catch(() => null)
    : null;

  if (!response.ok) {
    if (
      response.status === 401 &&
      onUnauthorized &&
      !path.startsWith("/auth/")
    ) {
      onUnauthorized();
    }

    const detail = data?.detail;

    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ??
          (response.status === 403
            ? "Accès refusé."
            : response.status === 404
              ? "Élément introuvable."
              : `Erreur ${response.status}`);

    throw new ApiError(response.status, message, detail, data?.errors);
  }

  return data as T;
}

/** Downloads a file from an authenticated GET endpoint. */
export async function download(
  path: string,
  query?: Query,
  fallbackName = "export",
): Promise<void> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}/api${path}${qs(query)}`, {
      credentials: "include",
      headers: {
        Accept: "*/*",
      },
    });
  } catch {
    throw new ApiError(
      0,
      "Impossible de joindre le serveur. Vérifiez votre connexion.",
      null,
    );
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      data?.detail ?? "Téléchargement impossible.",
      data,
    );
  }

  const blob = await response.blob();
  const contentDisposition =
    response.headers.get("content-disposition") ?? "";

  const filename =
    /filename="([^"]+)"/.exec(contentDisposition)?.[1] ?? fallbackName;

  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
   
