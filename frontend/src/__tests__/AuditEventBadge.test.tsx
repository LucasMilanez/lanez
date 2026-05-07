import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AuditEventBadge } from "@/components/AuditEventBadge";

describe("AuditEventBadge", () => {
  it("renders the event type label", () => {
    render(<AuditEventBadge eventType="auth.login" />);
    expect(screen.getByText("auth.login")).toBeInTheDocument();
  });

  it("applies inline color style for known types (auth.login uses green variable)", () => {
    render(<AuditEventBadge eventType="auth.login" />);
    const badge = screen.getByText("auth.login");
    // inline style should reference the CSS variable, not a hardcoded Tailwind class
    expect(badge.style.color).toBeTruthy();
    expect(badge.className).not.toContain("text-green-700");
  });

  it("renders without inline color style for unknown event types", () => {
    render(<AuditEventBadge eventType="unknown.type" />);
    const badge = screen.getByText("unknown.type");
    expect(badge.style.color).toBeFalsy();
  });
});
