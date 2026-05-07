import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";

interface StatusCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon?: ReactNode;
}

export function StatusCard({ title, value, description, icon }: StatusCardProps) {
  const isNumeric = typeof value === "number";

  return (
    <Card className="shadow-soft">
      <CardContent>
        <div className="flex items-start justify-between gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
          {icon && (
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-foreground">
              {icon}
            </div>
          )}
        </div>
        <div
          className={
            isNumeric
              ? "mt-3 font-display text-3xl font-semibold tabular-nums tracking-tight"
              : "mt-3 font-display text-base font-semibold leading-tight truncate"
          }
          title={isNumeric ? undefined : String(value)}
        >
          {value}
        </div>
        {description && (
          <p className="mt-1.5 text-xs text-muted-foreground line-clamp-2">
            {description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
