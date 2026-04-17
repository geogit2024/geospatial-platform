import { UsageSeriesPoint } from "@/lib/api";

interface UsageChartProps {
  data: UsageSeriesPoint[];
  title?: string;
}

function buildPoints(data: UsageSeriesPoint[], width: number, height: number, padding: number): string {
  if (!data.length) return "";

  const values = data.map((item) => item.total_gb);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return data
    .map((item, index) => {
      const x = padding + (index * (width - padding * 2)) / Math.max(data.length - 1, 1);
      const y = height - padding - ((item.total_gb - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");
}

export default function UsageChart({ data, title = "Uso de armazenamento" }: UsageChartProps) {
  const width = 680;
  const height = 180;
  const padding = 20;
  const points = buildPoints(data, width, height, padding);
  const firstLabel = data[0]?.date ?? "-";
  const lastLabel = data[data.length - 1]?.date ?? "-";

  return (
    <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
      <p className="text-sm font-semibold text-[#dbe8fb]">{title}</p>
      {!data.length ? (
        <p className="mt-3 text-sm text-[#7f97b5]">Sem dados suficientes para o grafico.</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${width} ${height}`} className="mt-3 h-40 w-full">
            <rect x="0" y="0" width={width} height={height} fill="#0c1727" rx="8" />
            <polyline
              fill="none"
              stroke="#38bdf8"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={points}
            />
          </svg>
          <div className="mt-2 flex items-center justify-between text-xs text-[#7f97b5]">
            <span>{firstLabel}</span>
            <span>{lastLabel}</span>
          </div>
        </>
      )}
    </div>
  );
}
