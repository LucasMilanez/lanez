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
        <YAxis fontSize={12} />
        <Tooltip />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={palette[entry.key]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
