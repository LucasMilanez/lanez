import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useTheme } from "@/theme/ThemeContext";

interface TokenUsageChartProps {
  data: { input: number; output: number; cache_read: number; cache_write: number };
}

function formatTokenValue(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function TokenUsageChart({ data }: TokenUsageChartProps) {
  const { resolvedTheme } = useTheme();

  const palette =
    resolvedTheme === "dark"
      ? {
          input: "#cbd5e1",
          output: "#94a3b8",
          cache_read: "#34d399",
          cache_write: "#38bdf8",
        }
      : {
          input: "#334155",
          output: "#64748b",
          cache_read: "#10b981",
          cache_write: "#0ea5e9",
        };

  const chartData = [
    { name: "Input", value: data.input, key: "input" as const },
    { name: "Output", value: data.output, key: "output" as const },
    { name: "Cache Read", value: data.cache_read, key: "cache_read" as const },
    { name: "Cache Write", value: data.cache_write, key: "cache_write" as const },
  ];

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="name" fontSize={12} />
        <YAxis
          fontSize={11}
          tickFormatter={formatTokenValue}
          label={{
            value: "tokens",
            angle: -90,
            position: "insideLeft",
            style: { fontSize: 11, fill: "hsl(215 16% 47%)" },
          }}
        />
        <Tooltip
          formatter={(value) => [Number(value).toLocaleString("pt-BR"), "tokens"]}
          contentStyle={{
            borderRadius: "0.5rem",
            border: "1px solid hsl(214 22% 89%)",
            fontSize: "12px",
          }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={palette[entry.key]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
