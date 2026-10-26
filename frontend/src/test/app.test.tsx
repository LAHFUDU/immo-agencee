import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ToastProvider } from "../components/ui";
import { api, qs, setCsrfToken } from "../lib/api";
import { AuthProvider } from "../lib/auth";
import { money, range } from "../lib/format";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("builds query strings without empty values", () => {
    expect(qs({ a: "1", b: "", c: undefined, d: ["x", "y"], e: false })).toBe("?a=1&d=x%2Cy&e=false");
  });

  it("sends the CSRF header on writes only", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { ok: true }));
    setCsrfToken("tok123");
    await api("/x");
    await api("/y", { body: { a: 1 } });
    const [, getInit] = spy.mock.calls[0];
    const [, postInit] = spy.mock.calls[1];
    expect((getInit!.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
    expect((postInit!.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    expect(postInit!.method).toBe("POST");
  });

  it("surfaces the server's French error message", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(409, { detail: "Ce bien est déjà réservé." }));
    await expect(api("/deals/1/reserve", { body: {} })).rejects.toThrow("Ce bien est déjà réservé.");
  });
});

describe("formatting", () => {
  it("formats money and ranges in French", () => {
    expect(money("1150000", "MAD").replace(/\s/g, " ")).toBe("1 150 000 MAD");
    expect(range(null, "900", (v) => v)).toBe("≤ 900");
  });
});

describe("routing & auth", () => {
  it("redirects anonymous users from the private area to the login page", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(401, { detail: "Authentification requise." }));
    renderAt("/app/requests");
    expect(await screen.findByRole("heading", { name: "Connexion" })).toBeInTheDocument();
  });

  it("shows the login error returned by the API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      String(input).includes("/auth/login") ? json(401, { detail: "Identifiants invalides." }) : json(401, { detail: "Authentification requise." }),
    );
    renderAt("/login");
    fireEvent.change(await screen.findByLabelText(/Adresse e-mail/), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(/Mot de passe/), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByText("Identifiants invalides.")).toBeInTheDocument();
  });

  it("hides pages the user's role does not grant", async () => {
    const me = { id: "1", email: "a@b.com", full_name: "Agent Test", role_name: "Agent", role_code: "commercial_agent", is_superadmin: false, must_change_password: false, language: "fr", permissions: ["dashboard.view", "requests.view"], csrf_token: "t" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/auth/me")) return json(200, me);
      if (url.includes("unread-count")) return json(200, { count: 0 });
      return json(200, { tasks: { overdue: 0, today: 0 }, scope: "mine" });
    });
    renderAt("/app/users");
    expect(await screen.findByText("Accès refusé")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("link", { name: /Utilisateurs/ })).not.toBeInTheDocument());
    expect(screen.getAllByRole("link", { name: /Demandes clients/ }).length).toBeGreaterThan(0);
  });
});
