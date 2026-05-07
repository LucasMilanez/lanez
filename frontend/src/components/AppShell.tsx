import { useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  History,
  Settings,
  LogOut,
  Sparkles,
  Menu,
  Brain,
} from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { MicButton } from "@/components/voice/MicButton";
import { ThemeToggle } from "@/theme/ThemeToggle";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/briefings", label: "Briefings", icon: FileText },
  { to: "/memories", label: "Memórias", icon: Brain },
  { to: "/audit", label: "Auditoria", icon: History },
  { to: "/settings", label: "Configurações", icon: Settings },
];

const pageTitles: Record<string, { title: string; description: string }> = {
  "/dashboard": {
    title: "Dashboard",
    description: "Visão geral das integrações e atividade recente",
  },
  "/briefings": {
    title: "Briefings",
    description: "Histórico de preparações automáticas de reunião",
  },
  "/memories": {
    title: "Memórias",
    description: "Contexto persistente guardado para sessões futuras",
  },
  "/audit": {
    title: "Auditoria",
    description: "Trilha imutável de acessos aos seus dados",
  },
  "/settings": {
    title: "Configurações",
    description: "Preferências da conta e da aplicação",
  },
};

function getPageMeta(pathname: string) {
  const match = Object.keys(pageTitles).find((key) => pathname.startsWith(key));
  return match ? pageTitles[match] : { title: "", description: "" };
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { title, description } = getPageMeta(location.pathname);
  const userInitial = (user?.email?.[0] ?? "?").toUpperCase();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col bg-card border-r border-border transition-transform duration-200 ease-in-out",
          "md:relative md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        <div className="px-5 pt-6 pb-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand text-brand-foreground shadow-soft">
              <Sparkles className="h-4 w-4" strokeWidth={2.25} />
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-display text-base font-semibold tracking-tight">
                Lanez
              </span>
              <span className="text-[11px] text-muted-foreground mt-0.5">
                MCP · Microsoft 365
              </span>
            </div>
          </div>
        </div>

        <Separator />

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Navegação
          </p>
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                {active && (
                  <span className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-brand" />
                )}
                <Icon
                  className={cn(
                    "h-4 w-4",
                    active
                      ? "text-foreground"
                      : "text-muted-foreground group-hover:text-foreground",
                  )}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <Separator />

        <div className="p-3 space-y-2">
          <div className="flex items-center gap-3 rounded-md px-2 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary text-secondary-foreground text-xs font-semibold">
              {userInitial}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-foreground">
                {user?.email ?? "—"}
              </p>
              <p className="text-[10px] text-muted-foreground">Conectado</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground hover:text-foreground"
            onClick={() => void logout()}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Sair
          </Button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-30 h-16 border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4 md:px-8 flex items-center justify-between gap-4">
          {/* Hamburger — mobile only */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden shrink-0"
            onClick={() => setMobileOpen(true)}
            aria-label="Abrir menu de navegação"
          >
            <Menu className="h-5 w-5" />
          </Button>

          <div className="min-w-0 flex-1">
            <h1 className="font-display text-base font-semibold tracking-tight text-foreground">
              {title}
            </h1>
            {description && (
              <p className="text-xs text-muted-foreground truncate">
                {description}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <MicButton />
            <Separator orientation="vertical" className="h-5" />
            <ThemeToggle />
          </div>
        </header>
        <div className="flex-1 overflow-auto">
          <div className="p-4 md:p-8 max-w-6xl mx-auto">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
