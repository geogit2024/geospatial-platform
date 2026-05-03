import { UsageSeriesPoint } from "@/lib/api";

interface UsageChartProps {
  data: UsageSeriesPoint[];
  title?: string;
}

function formatGb(value: number): string {
  if (value >= 100) return `${value.toFixed(0)} GB`;
  if (value >= 10) return `${value.toFixed(1)} GB`;
  return `${value.toFixed(2)} GB`;
}

export default function UsageChart({ data, title = "Uso de armazenamento" }: UsageChartProps) {
  const width = 680;
  const height = 180;
  const padding = 24;
  const leftPadding = 72;
  const rightPadding = 24;
  const yTicks = 4;
  const xTicks = Math.max(3, Math.min(data.length - 1, 8));
  const values = data.map((item) => item.total_gb);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const range = max - min || 1;
  const chartWidth = width - leftPadding - rightPadding;
  const chartHeight = height - padding * 2;
  const points = data
    .map((item, index) => {
      const x = leftPadding + (index * chartWidth) / Math.max(data.length - 1, 1);
      const y = height - padding - ((item.total_gb - min) / range) * chartHeight;
      return `${x},${y}`;
    })
    .join(" ");
  const coordinates = data.map((item, index) => ({
    x: leftPadding + (index * chartWidth) / Math.max(data.length - 1, 1),
    y: height - padding - ((item.total_gb - min) / range) * chartHeight,
  }));
  const firstLabel = data[0]?.date ?? "-";
  const lastLabel = data[data.length - 1]?.date ?? "-";
  const lastPoint = data[data.length - 1];
  const lastCoordinate = coordinates[coordinates.length - 1];

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
              const value = max - ratio * range;
              return (
                <g key={`usage-y-grid-${i}`}>
                  <text
                    x={leftPadding - 10}
                    y={y + 4}
                    textAnchor="end"
                    className="fill-[#8aa4c5] text-[10px]"
                  >
                    {formatGb(value)}
                  </text>
                  <line
                    x1={leftPadding}
                    y1={y}
                    x2={width - rightPadding}
                    y2={y}
                    stroke="#2b4463"
                    strokeDasharray="4 4"
                  />
                </g>
              );
            })}
            {Array.from({ length: xTicks + 1 }, (_, i) => {
              const ratio = i / Math.max(xTicks, 1);
              const x = leftPadding + ratio * chartWidth;
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
              >
                <title>{`${data[index].date}: ${formatGb(data[index].total_gb)}`}</title>
              </circle>
            ))}
            {lastPoint && lastCoordinate && (
              <g>
                <rect
                  x={Math.min(lastCoordinate.x - 92, width - 142)}
                  y={Math.max(lastCoordinate.y - 30, 8)}
                  width="118"
                  height="22"
                  rx="6"
                  fill="#12243a"
                  stroke="#2b557a"
                />
                <text
                  x={Math.min(lastCoordinate.x - 82, width - 132)}
                  y={Math.max(lastCoordinate.y - 15, 23)}
                  className="fill-[#dff4ff] text-[11px] font-semibold"
                >
                  {formatGb(lastPoint.total_gb)}
                </text>
              </g>
            )}
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
