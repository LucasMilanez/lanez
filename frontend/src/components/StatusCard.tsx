import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatusCardVariant = "default" | "destructive" | "clickable";

interface StatusCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon?: ReactNode;
  variant?: StatusCardVariant;
  badge?: string;
}

export function StatusCard({
  title,
  value,
  description,
  icon,
  variant = "default",
  badge,
}: StatusCardProps) {
  const isNumeric = typeof value === "number";
  const isClickable = variant === "clickable";
  const isDestructive = variant === "destructive";

  return (
    <Card
      className={cn(
        "shadow-soft transition-all duration-150 h-full",
        isClickable && "cursor-pointer hover:border-brand/40 hover:shadow-elevated group",
        isDestructive && "border-destructive/30 bg-destructive/[0.03]",
      )}
      role={isClickable ? "button" : undefined}
      aria-label={isClickable ? `${title}: ${value}. ${description ?? ""}` : undefined}
    >
      <CardContent className="h-full flex flex-col p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground leading-tight">
            {title}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            {badge && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[9px] font-semibold whitespace-nowrap",
                  isDestructive
                    ? "bg-destructive/10 text-destructive"
                    : "bg-brand/10 text-brand",
                )}
              >
                {badge}
              </span>
            )}
            {icon && (
              <div
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                  isDestructive
                    ? "bg-destructive/10 text-destructive"
                    : "bg-accent text-foreground",
                )}
              >
                {icon}
              </div>
            )}
            {isClickable && (
              <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            )}
          </div>
        </div>
        <div
          className={cn(
            "mt-2 min-w-0",
            isNumeric
              ? "font-display text-2xl font-semibold tabular-nums tracking-tight"
              : "font-display text-sm font-semibold leading-tight truncate",
            isDestructive && "text-destructive",
          )}
          title={isNumeric ? undefined : String(value)}
        >
          {value}
        </div>
        {description && (
          <p className="mt-1 text-[11px] text-muted-foreground truncate">
            {description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
