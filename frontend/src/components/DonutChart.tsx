import { memo } from "react";

interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  segments: DonutSegment[];
  size?: number;
  strokeWidth?: number;
  centerLabel?: string;
  centerValue?: string;
}

/**
 * SVG donut chart with configurable segments.
 * Rotated -90deg so the first segment starts at 12 o'clock.
 */
export const DonutChart = memo(function DonutChart({
  segments,
  size = 120,
  strokeWidth = 3.4,
  centerLabel,
  centerValue,
}: DonutChartProps) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) return null;

  const radius = 15.9155;
  let offset = 0;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg
        className="h-full w-full"
        viewBox="0 0 36 36"
        style={{ transform: "rotate(-90deg)" }}
      >
        {/* Background ring */}
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="transparent"
          stroke="hsl(var(--border))"
          strokeWidth={strokeWidth}
        />
        {/* Segments */}
        {segments.map((seg) => {
          const pct = (seg.value / total) * 100;
          const dashArray = `${pct} ${100 - pct}`;
          const dashOffset = -offset;
          offset += pct;
          return (
            <circle
              key={seg.label}
              cx="18"
              cy="18"
              r={radius}
              fill="transparent"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={dashArray}
              strokeDashoffset={dashOffset}
            />
          );
        })}
      </svg>
      {(centerLabel || centerValue) && (
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            {centerLabel && (
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {centerLabel}
              </div>
            )}
            {centerValue && (
              <div className="text-sm font-semibold tabular-nums text-foreground">
                {centerValue}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
});
