import { Navigate } from "react-router-dom";
import { Sparkles, Shield, Zap, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/AuthContext";

export function LoginPage() {
  const { login, user, loading } = useAuth();

  if (loading) return null;
  if (user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="min-h-screen bg-background text-foreground grid lg:grid-cols-2">
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-border bg-card p-10">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 10%, hsl(var(--brand) / 0.18), transparent 45%), radial-gradient(circle at 80% 80%, hsl(var(--brand) / 0.10), transparent 50%)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
            opacity: 0.18,
            maskImage:
              "radial-gradient(ellipse at center, black 30%, transparent 75%)",
          }}
        />

        <div className="relative flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-brand-foreground shadow-soft">
            <Sparkles className="h-4 w-4" strokeWidth={2.25} />
          </div>
          <span className="font-display text-lg font-semibold tracking-tight">
            Lanez
          </span>
        </div>

        <div className="relative space-y-8 max-w-md">
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-brand">
              MCP Server pessoal
            </p>
            <h2 className="font-display text-3xl font-semibold tracking-tight text-balance leading-tight">
              Seu Microsoft 365 conectado a qualquer assistente de IA.
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Calendário, e-mail, OneNote e OneDrive disponíveis via MCP — com
              busca semântica, memória persistente e briefings gerados
              automaticamente.
            </p>
          </div>

          <ul className="space-y-3.5 text-sm">
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-foreground">
                <Zap className="h-3.5 w-3.5" />
              </span>
              <div>
                <p className="font-medium">Tempo real via Graph Webhooks</p>
                <p className="text-xs text-muted-foreground">
                  Sem polling, sem rate limit desperdiçado.
                </p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-foreground">
                <Shield className="h-3.5 w-3.5" />
              </span>
              <div>
                <p className="font-medium">Audit trail imutável</p>
                <p className="text-xs text-muted-foreground">
                  Cada acesso aos seus dados fica registrado.
                </p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-foreground">
                <Lock className="h-3.5 w-3.5" />
              </span>
              <div>
                <p className="font-medium">OAuth 2.0 + tokens criptografados</p>
                <p className="text-xs text-muted-foreground">
                  Seus tokens nunca saem do banco em texto claro.
                </p>
              </div>
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-muted-foreground">
          Open source · self-hosted · sem custo de licença
        </p>
      </aside>

      <section className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm space-y-8">
          <div className="lg:hidden flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-brand text-brand-foreground shadow-soft">
              <Sparkles className="h-4 w-4" strokeWidth={2.25} />
            </div>
            <span className="font-display text-lg font-semibold tracking-tight">
              Lanez
            </span>
          </div>

          <div className="space-y-2">
            <h1 className="font-display text-2xl font-semibold tracking-tight">
              Entrar
            </h1>
            <p className="text-sm text-muted-foreground">
              Use sua conta Microsoft 365 para acessar o painel.
            </p>
          </div>

          <Button className="w-full h-11" onClick={login}>
            Entrar com Microsoft
          </Button>

          <p className="text-[11px] text-muted-foreground leading-relaxed">
            Ao entrar, você autoriza o Lanez a ler seu calendário, e-mail,
            OneNote e OneDrive via Microsoft Graph API. Você pode revogar o
            acesso a qualquer momento no portal da Microsoft.
          </p>
        </div>
      </section>
    </div>
  );
}
