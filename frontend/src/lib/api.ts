/**
 * Cliente HTTP fino. Todas as requests vão para a mesma origem
 * (Vite proxy encaminha em dev). Cookies são enviados automaticamente
 * porque é same-origin do ponto de vista do browser.
 */
import { demoGet, demoWrite, isDemoMode } from "@/demo/demoRouter";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Header utilizado como defesa em profundidade contra CSRF.
 * Navegação direta (click em link, form submit cross-site) não envia
 * este header — apenas requests XHR/fetch explícitos do nosso código.
 * O backend pode ser configurado para exigi-lo em rotas de mutação.
 */
const CSRF_HEADER = { "X-Requested-With": "XMLHttpRequest" } as const;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Demo mode short-circuit — serves fixtures without a backend.
  if (isDemoMode) {
    const method = init?.method ?? "GET";
    if (method === "GET") {
      const stub = demoGet(path);
      if (stub !== undefined) return stub as T;
    } else {
      let parsed: unknown = undefined;
      if (typeof init?.body === "string") {
        try {
          parsed = JSON.parse(init.body);
        } catch {
          parsed = init.body;
        }
      }
      return demoWrite(method, path, parsed) as T;
    }
  }

  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...CSRF_HEADER,
      ...init?.headers,
    },
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // resposta não é JSON; mantém statusText
    }
    throw new ApiError(response.status, detail);
  }

  // DELETE / métodos sem body podem retornar 200 vazio ou sem JSON
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  if (isDemoMode) {
    // Voice transcription stub in demo mode.
    if (path === "/voice/transcribe") {
      return {
        transcription: "Demo mode — transcription is disabled. Connect a real backend to enable Groq Whisper.",
        duration_ms: 320,
      } as T;
    }
    return undefined as T;
  }

  const response = await fetch(path, {
    method: "POST",
    body: formData, // NÃO setar Content-Type — fetch + FormData fazem com boundary correto
    headers: { ...CSRF_HEADER },
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* mantém statusText */
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postMultipart: <T>(path: string, formData: FormData) =>
    requestMultipart<T>(path, formData),
};
