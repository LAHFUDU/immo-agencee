const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

export function money(v: string | number | null | undefined, currency = "MAD"): string {
  if (v === null || v === undefined || v === "") return "—";
  return `${nf.format(Number(v))} ${currency}`;
}

export function num(v: string | number | null | undefined, suffix = ""): string {
  if (v === null || v === undefined || v === "") return "—";
  return `${nf2.format(Number(v))}${suffix}`;
}

export function date(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function relative(v: string | null | undefined): string {
  if (!v) return "—";
  const diff = (new Date(v).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
  return date(v);
}

/** <input type="datetime-local"> value <-> ISO string (local time). */
export function toLocalInput(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(v: string): string | null {
  return v ? new Date(v).toISOString() : null;
}

export function range(min: string | null | undefined, max: string | null | undefined, fmt: (v: string) => string): string {
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  if (max) return `≤ ${fmt(max)}`;
  if (min) return `≥ ${fmt(min)}`;
  return "—";
}
