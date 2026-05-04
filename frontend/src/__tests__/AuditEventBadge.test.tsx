import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AuditEventBadge } from "@/components/AuditEventBadge";

describe("AuditEventBadge", () => {
  it("applies green classes for auth.login", () => {
    render(<AuditEventBadge eventType="auth.login" />);
    const badge = screen.getByText("auth.login");
    expect(badge.className).toContain("text-green-700");
  });

  it("applies purple classes for mcp.call", () => {
    render(<AuditEventBadge eventType="mcp.call" />);
    const badge = screen.getByText("mcp.call");
    expect(badge.className).toContain("text-purple-700");
  });

  it("applies fallback classes for unknown type", () => {
    render(<AuditEventBadge eventType="unknown.type" />);
    const badge = screen.getByText("unknown.type");
    expect(badge.className).toContain("bg-muted");
    expect(badge.className).toContain("text-muted-foreground");
  });
});
