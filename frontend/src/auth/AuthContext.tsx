import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { isDemoMode } from "@/demo/demoRouter";

export interface User {
  id: string;
  email: string;
  token_expires_at: string;
  last_sync_at: string | null;
  created_at: string;
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const login = () => {
    // Demo mode: jump straight to the dashboard with the fake user.
    if (isDemoMode) {
      window.location.href = `${window.location.origin}/dashboard`;
      return;
    }

    const returnUrl = `${window.location.origin}/dashboard`;
    // In production, redirect directly to the Fly.io backend to avoid
    // Vercel proxy issues with OAuth 302 redirects.
    const apiBase = import.meta.env.VITE_API_BASE_URL
      || (window.location.hostname === "lanez.vercel.app" ? "https://lanez-app.fly.dev" : "");
    window.location.href = `${apiBase}/auth/microsoft?return_url=${encodeURIComponent(returnUrl)}`;
  };

  const logout = async () => {
    await api.post("/auth/logout");
    setUser(null);
    window.location.href = "/";
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
