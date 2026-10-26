import clsx from "clsx";
import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Loader2, X } from "lucide-react";
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";

// ---------------------------------------------------------------- buttons

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "gold";
const btnStyles: Record<BtnVariant, string> = {
  primary: "bg-brand-800 text-white hover:bg-brand-700 shadow-sm",
  secondary: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shadow-sm",
  ghost: "text-slate-600 hover:bg-slate-100",
  danger: "bg-red-600 text-white hover:bg-red-700 shadow-sm",
  gold: "bg-gold-500 text-brand-950 hover:bg-gold-300 shadow-sm",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode }
>(function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest }, ref) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        btnStyles[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- form controls

const control =
  "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-800 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none disabled:bg-slate-100";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={clsx(control, className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, rows = 3, ...rest },
  ref,
) {
  return <textarea ref={ref} rows={rows} className={clsx(control, className)} {...rest} />;
});

export function Select({
  options,
  placeholder,
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[]; placeholder?: string }) {
  return (
    <select className={clsx(control, "pr-8", className)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Field({
  label,
  error,
  hint,
  required,
  children,
  className,
}: {
  label: string;
  error?: string | null;
  hint?: string;
  required?: boolean;
  children: (id: string) => ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
        {required && <span className="text-red-600"> *</span>}
      </label>
      {children(id)}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function Checkbox({ label, checked, onChange, disabled }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className={clsx("inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700", disabled && "opacity-50")}>
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-slate-300 text-brand-700 focus:ring-brand-300"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

// ---------------------------------------------------------------- layout

export function Card({ children, className, title, actions }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={clsx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {back}
        <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-slate-500">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function KV({ items, cols = 2 }: { items: [string, ReactNode][]; cols?: 1 | 2 | 3 }) {
  return (
    <dl className={clsx("grid gap-x-6 gap-y-3", cols === 1 ? "grid-cols-1" : cols === 2 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1 sm:grid-cols-3")}>
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{k}</dt>
          <dd className="mt-0.5 break-words text-sm text-slate-800">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="scrollbar-thin mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            value === t.value ? "border-brand-700 text-brand-800" : "border-transparent text-slate-500 hover:text-slate-700",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- badges

const badgeColors = {
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  teal: "bg-brand-50 text-brand-800 ring-brand-200",
};
export type BadgeColor = keyof typeof badgeColors;

export function Badge({ color = "gray", children, className }: { color?: BadgeColor; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", badgeColors[color], className)}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- feedback states

export function Spinner({ label = "Chargement…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Une erreur est survenue.";
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-8 text-center text-sm text-red-700" role="alert">
      <AlertTriangle className="h-6 w-6" aria-hidden />
      <p>{msg}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Réessayer
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <div className="text-slate-300">{icon ?? <Inbox className="h-10 w-10" aria-hidden />}</div>
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function Alert({ color = "amber", children, title }: { color?: "amber" | "red" | "green" | "blue"; children: ReactNode; title?: string }) {
  const c = {
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    red: "border-red-200 bg-red-50 text-red-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-900",
    blue: "border-sky-200 bg-sky-50 text-sky-900",
  }[color];
  return (
    <div className={clsx("rounded-lg border px-4 py-3 text-sm", c)} role="status">
      {title && <p className="mb-0.5 font-semibold">{title}</p>}
      {children}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="flex items-center justify-between gap-2 px-1 pt-3 text-sm text-slate-600" aria-label="Pagination">
      <span>
        {from}–{to} sur {total}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Page précédente">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-2">
          {page} / {pages}
        </span>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Page suivante">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

export function StatCard({ label, value, hint, icon, tone = "teal", onClick }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "teal" | "gold" | "red" | "slate" | "green"; onClick?: () => void }) {
  const toneCls = {
    teal: "bg-brand-50 text-brand-700",
    gold: "bg-gold-100 text-gold-700",
    red: "bg-red-50 text-red-600",
    slate: "bg-slate-100 text-slate-600",
    green: "bg-emerald-50 text-emerald-700",
  }[tone];
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      className={clsx("flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm", onClick && "transition hover:border-brand-300 hover:shadow")}
    >
      {icon && <div className={clsx("rounded-lg p-2", toneCls)}>{icon}</div>}
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
      </div>
    </Comp>
  );
}

// ---------------------------------------------------------------- modal & confirm

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-close])");
    first?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={clsx("flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}
      >
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 id={titleId} className="font-semibold text-slate-900">
            {title}
          </h2>
          <button data-close onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Fermer">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmButton({
  children,
  title,
  message,
  confirmLabel = "Confirmer",
  onConfirm,
  variant = "secondary",
  danger = false,
  size,
  icon,
  disabled,
}: {
  children: ReactNode;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: () => Promise<unknown> | void;
  variant?: BtnVariant;
  danger?: boolean;
  size?: "sm" | "md";
  icon?: ReactNode;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  return (
    <>
      <Button variant={variant} size={size} icon={icon} disabled={disabled} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Annuler
            </Button>
            <Button
              variant={danger ? "danger" : "primary"}
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onConfirm();
                  setOpen(false);
                } catch (e) {
                  toast.error(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {confirmLabel}
            </Button>
          </>
        }
      >
        <div className="text-sm text-slate-600">{message}</div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------- toasts

interface ToastItem {
  id: number;
  kind: "success" | "error" | "info";
  text: string;
}
const ToastCtx = createContext<{ success: (t: string) => void; error: (e: unknown) => void; info: (t: string) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((kind: ToastItem["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);
  const api = useRef({
    success: (t: string) => push("success", t),
    info: (t: string) => push("info", t),
    error: (e: unknown) => push("error", e instanceof Error ? e.message : String(e)),
  });
  return (
    <ToastCtx.Provider value={api.current}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:items-end" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "pointer-events-auto max-w-md rounded-lg px-4 py-3 text-sm shadow-lg",
              t.kind === "success" && "bg-emerald-700 text-white",
              t.kind === "error" && "bg-red-700 text-white",
              t.kind === "info" && "bg-slate-800 text-white",
            )}
            role={t.kind === "error" ? "alert" : "status"}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const c = useContext(ToastCtx);
  if (!c) throw new Error("useToast outside ToastProvider");
  return c;
}
