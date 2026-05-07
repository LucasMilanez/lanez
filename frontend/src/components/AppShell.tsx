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
import { useI18n } from "@/i18n/I18nContext";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { MicButton } from "@/components/voice/MicButton";
import { ThemeToggle } from "@/theme/ThemeToggle";
import { LocaleToggle } from "@/i18n/LocaleToggle";
import { cn } from "@/lib/utils";

const navKeys = [
  { to: "/dashboard", key: "dashboard" as const, icon: LayoutDashboard },
  { to: "/briefings", key: "briefings" as const, icon: FileText },
  { to: "/memories", key: "memories" as const, icon: Brain },
  { to: "/audit", key: "audit" as const, icon: History },
  { to: "/settings", key: "settings" as const, icon: Settings },
];


export function AppShell() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const location = useLocation();
  const userInitial = (user?.email?.[0] ?? "?").toUpperCase();
  const [mobileOpen, setMobileOpen] = useState(false);

  const pageKey = navKeys.find((item) => location.pathname.startsWith(item.to))?.key;
  const title = pageKey ? t.pages[pageKey].title : "";
  const description = pageKey ? t.pages[pageKey].description : "";

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
            {t.nav.navigation}
          </p>
          {navKeys.map((item) => {
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
                {t.nav[item.key]}
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
              <p className="text-[10px] text-muted-foreground">{t.common.connected}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground hover:text-foreground"
            onClick={() => void logout()}
          >
            <LogOut className="h-4 w-4 mr-2" />
            {t.nav.logout}
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
            aria-label={t.nav.openMenu}
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
            <LocaleToggle />
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
