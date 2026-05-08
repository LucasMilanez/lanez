import { isDemoMode } from "./demoRouter";

/**
 * Small corner badge visible only when VITE_DEMO_MODE=true. Makes it
 * obvious in screenshots that the data is synthetic. Remove from the
 * frame if you want a clean capture.
 */
export function DemoBadge() {
  if (!isDemoMode) return null;

  return (
    <div
      className="fixed bottom-3 right-3 z-[9999] pointer-events-none select-none"
      aria-hidden="true"
    >
      <span
        className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-wider text-amber-500 backdrop-blur"
        style={{ letterSpacing: "0.14em" }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
        demo data
      </span>
    </div>
  );
}
