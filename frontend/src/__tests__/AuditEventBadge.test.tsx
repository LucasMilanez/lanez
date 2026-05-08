import { screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { renderWithProviders, setLocale } from "./test-utils";
import { AuditEventBadge } from "@/components/AuditEventBadge";

describe("AuditEventBadge", () => {
  beforeEach(() => {
    // Garantir locale conhecido: o badge mapeia "auth.login" → "Login".
    setLocale("pt");
  });

  it("renders the translated event type label", () => {
    // `withRouter: false` porque o componente não usa rotas.
    renderWithProviders(<AuditEventBadge eventType="auth.login" />, { withRouter: false });
    // O label traduzido ("Login") aparece no DOM; o tipo técnico fica no `title`.
    expect(screen.getByText("Login")).toBeInTheDocument();
    expect(screen.getByText("Login").closest("[title]")?.getAttribute("title")).toBe(
      "auth.login",
    );
  });

  it("applies inline color style for known types (auth.login uses green variable)", () => {
    renderWithProviders(<AuditEventBadge eventType="auth.login" />, { withRouter: false });
    const badge = screen.getByText("Login");
    expect(badge.style.color).toBeTruthy();
    expect(badge.className).not.toContain("text-green-700");
  });

  it("renders without inline color style for unknown event types", () => {
    renderWithProviders(<AuditEventBadge eventType="unknown.type" />, { withRouter: false });
    // Eventos desconhecidos caem no fallback → exibem o próprio eventType.
    const badge = screen.getByText("unknown.type");
    expect(badge.style.color).toBeFalsy();
  });
});
