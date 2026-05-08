/**
 * Demo router — resolves API paths to fixture data when VITE_DEMO_MODE=true.
 *
 * Returns `undefined` for paths the demo doesn't cover, so the real `api`
 * client can fall through. Keep this list synchronized with the fixtures.
 */
import {
  demoAuthToken,
  demoAuditPage1,
  demoBriefingDetail,
  demoBriefingsPage1,
  demoMemories,
  demoStatus,
  demoUser,
} from "./fixtures";

export const isDemoMode: boolean = import.meta.env.VITE_DEMO_MODE === "true";

/**
 * Returns a stub value for GET requests in demo mode, or undefined if the
 * path is not mocked (caller should fall back to the real network).
 */
export function demoGet(path: string): unknown | undefined {
  if (path === "/auth/me") return demoUser;
  if (path === "/status") return demoStatus;
  if (path === "/auth/token") return demoAuthToken;
  if (path === "/memories") return demoMemories;

  if (path.startsWith("/briefings/")) {
    return demoBriefingDetail;
  }
  if (path.startsWith("/briefings")) {
    return demoBriefingsPage1;
  }
  if (path.startsWith("/audit")) {
    return demoAuditPage1;
  }
  return undefined;
}

/**
 * Returns a stub value for POST/PATCH/DELETE in demo mode. Writes are
 * acknowledged with a success shape so toasts still fire, but nothing is
 * persisted — every refresh shows the same snapshot.
 */
export function demoWrite(method: string, path: string, body?: unknown): unknown {
  // Memory create: echo back with a fake id
  if (method === "POST" && path === "/memories") {
    const b = (body ?? {}) as { content?: string; tags?: string[] };
    return {
      id: `demo-${Date.now()}`,
      content: b.content ?? "",
      tags: b.tags ?? [],
      created_at: new Date().toISOString(),
    };
  }

  // Memory patch: echo the edited body
  if (method === "PATCH" && path.startsWith("/memories/")) {
    const b = (body ?? {}) as { content?: string; tags?: string[] };
    const original = demoMemories[0];
    return {
      id: path.split("/").pop(),
      content: b.content ?? original.content,
      tags: b.tags ?? original.tags,
      created_at: original.created_at,
    };
  }

  // Logout, delete, refresh, etc. — return empty success
  return undefined;
}
