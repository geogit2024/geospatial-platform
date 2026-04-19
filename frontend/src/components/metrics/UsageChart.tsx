import { UsageSeriesPoint } from "@/lib/api";

interface UsageChartProps {
  data: UsageSeriesPoint[];
  title?: string;
}

type ChartPoint = {
  x: number;
  y: number;
};

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

function buildCoordinates(data: UsageSeriesPoint[], width: number, height: number, padding: number): ChartPoint[] {
  if (!data.length) return [];

  const values = data.map((item) => item.total_gb);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return data.map((item, index) => ({
    x: padding + (index * (width - padding * 2)) / Math.max(data.length - 1, 1),
    y: height - padding - ((item.total_gb - min) / range) * (height - padding * 2),
  }));
}

export default function UsageChart({ data, title = "Uso de armazenamento" }: UsageChartProps) {
  const width = 680;
  const height = 180;
  const padding = 20;
  const yTicks = 4;
  const xTicks = Math.max(3, Math.min(data.length - 1, 8));
  const points = buildPoints(data, width, height, padding);
  const coordinates = buildCoordinates(data, width, height, padding);
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
            {Array.from({ length: yTicks + 1 }, (_, i) => {
              const ratio = i / yTicks;
              const y = padding + ratio * (height - padding * 2);
              return (
                <line
                  key={`usage-y-grid-${i}`}
                  x1={padding}
                  y1={y}
                  x2={width - padding}
                  y2={y}
                  stroke="#2b4463"
                  strokeDasharray="4 4"
                />
              );
            })}
            {Array.from({ length: xTicks + 1 }, (_, i) => {
              const ratio = i / Math.max(xTicks, 1);
              const x = padding + ratio * (width - padding * 2);
              return (
                <line
                  key={`usage-x-grid-${i}`}
                  x1={x}
                  y1={padding}
                  x2={x}
                  y2={height - padding}
                  stroke="#223850"
                  strokeDasharray="3 6"
                />
              );
            })}
            <polyline
              fill="none"
              stroke="#00e5ff"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={points}
            />
            {coordinates.map((point, index) => (
              <circle
                key={`usage-point-${index}`}
                cx={point.x}
                cy={point.y}
                r={index === coordinates.length - 1 ? 3.2 : 2.2}
                fill={index === coordinates.length - 1 ? "#ff4d6d" : "#00e5ff"}
              />
            ))}
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
