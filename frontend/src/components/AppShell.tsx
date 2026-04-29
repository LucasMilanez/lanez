import { Outlet, Link, useLocation } from "react-router-dom";
import { LayoutDashboard, FileText, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { MicButton } from "@/components/voice/MicButton";
import { ThemeToggle } from "@/theme/ThemeToggle";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/briefings", label: "Briefings", icon: FileText },
  { to: "/settings", label: "Configurações", icon: Settings },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside className="w-60 bg-card border-r border-border flex flex-col">
        <div className="px-6 py-5 text-2xl font-semibold tracking-tight">
          Lanez
        </div>
        <nav className="flex-1 px-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-border">
          <Button
            variant="ghost"
            className="w-full justify-start"
            onClick={() => void logout()}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Sair
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <header className="h-14 border-b border-border bg-card px-6 flex items-center justify-end gap-3 text-sm text-muted-foreground">
          <span>{user?.email}</span>
          <MicButton />
          <ThemeToggle />
        </header>
        <div className="p-6 max-w-6xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
