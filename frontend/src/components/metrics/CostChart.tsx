import { CostSeriesPoint } from "@/lib/api";

interface CostChartProps {
  data: CostSeriesPoint[];
  title?: string;
  currency?: string;
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(value);
}

function formatDateLabel(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  if (!year || !month || !day) return date;
  return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}`;
}

type BarLayout = {
  x: number;
  w: number;
  storageY: number;
  storageH: number;
  processingY: number;
  processingH: number;
  downloadsY: number;
  downloadsH: number;
  totalY: number;
};

function buildBars(
  data: CostSeriesPoint[],
  width: number,
  height: number,
  padding: { top: number; right: number; bottom: number; left: number }
) {
  if (!data.length) return [] as BarLayout[];

  const max = Math.max(...data.map((item) => item.value), 1);
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const slot = chartWidth / data.length;
  const barWidth = Math.max(Math.min(slot * 0.62, 24), data.length === 1 ? 64 : 5);

  return data.map((item, index) => {
    const x = padding.left + index * slot + (slot - barWidth) / 2;
    const totalH = (chartHeight * item.value) / max;
    const storageH = (chartHeight * item.storage) / max;
    const processingH = (chartHeight * item.processing) / max;
    const downloadsH = (chartHeight * item.downloads) / max;

    const chartBottom = padding.top + chartHeight;
    const totalY = chartBottom - totalH;

    const storageY = chartBottom - storageH;
    const processingY = storageY - processingH;
    const downloadsY = processingY - downloadsH;

    return {
      x,
      w: barWidth,
      storageY,
      storageH,
      processingY,
      processingH,
      downloadsY,
      downloadsH,
      totalY,
    };
  });
}

export default function CostChart({ data, title = "Evolucao de custo", currency = "BRL" }: CostChartProps) {
  const width = 680;
  const height = 220;
  const padding = { top: 20, right: 16, bottom: 36, left: 68 };
  const bars = buildBars(data, width, height, padding);
  const max = Math.max(...data.map((item) => item.value), 1);
  const avg = data.length ? data.reduce((sum, item) => sum + item.value, 0) / data.length : 0;
  const latest = data[data.length - 1];
  const peak = data.reduce<CostSeriesPoint | null>(
    (acc, item) => (!acc || item.value > acc.value ? item : acc),
    null
  );
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const yTicks = 4;
  const xStride = Math.max(1, Math.ceil(data.length / 6));

  return (
    <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-semibold text-[#dbe8fb]">{title}</p>
        {data.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#7f97b5]">
            <span>
              Ultimo: <strong className="text-[#dbe8fb]">{formatCurrency(latest?.value ?? 0, currency)}</strong>
            </span>
            <span>
              Media diaria: <strong className="text-[#dbe8fb]">{formatCurrency(avg, currency)}</strong>
            </span>
            <span>
              Pico: {" "}
              <strong className="text-[#dbe8fb]">
                {formatCurrency(peak?.value ?? 0, currency)} ({formatDateLabel(peak?.date ?? "-")})
              </strong>
            </span>
          </div>
        )}
      </div>

      {!data.length ? (
        <p className="mt-3 text-sm text-[#7f97b5]">Sem dados suficientes para o grafico.</p>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} className="mt-3 h-48 w-full">
          <rect x="0" y="0" width={width} height={height} fill="#0c1727" rx="8" />

          {Array.from({ length: yTicks + 1 }, (_, i) => {
            const ratio = i / yTicks;
            const y = padding.top + ratio * chartHeight;
            const tickValue = max * (1 - ratio);
            return (
              <g key={`y-grid-${i}`}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={padding.left + chartWidth}
                  y2={y}
                  stroke="#2a3f58"
                  strokeDasharray="4 4"
                />
                <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize="10" fill="#7f97b5">
                  {formatCurrency(tickValue, currency)}
                </text>
              </g>
            );
          })}

          <line
            x1={padding.left}
            y1={padding.top + chartHeight}
            x2={padding.left + chartWidth}
            y2={padding.top + chartHeight}
            stroke="#365473"
          />

          {bars.map((bar, index) => (
            <g key={index}>
              {bar.storageH > 0 && (
                <rect x={bar.x} y={bar.storageY} width={bar.w} height={bar.storageH} rx="2" fill="#38bdf8">
                  <title>
                    {`${formatDateLabel(data[index].date)} | Storage: ${formatCurrency(data[index].storage, currency)}`}
                  </title>
                </rect>
              )}
              {bar.processingH > 0 && (
                <rect
                  x={bar.x}
                  y={bar.processingY}
                  width={bar.w}
                  height={bar.processingH}
                  rx="2"
                  fill="#34d399"
                >
                  <title>
                    {`${formatDateLabel(data[index].date)} | Processamento: ${formatCurrency(data[index].processing, currency)}`}
                  </title>
                </rect>
              )}
              {bar.downloadsH > 0 && (
                <rect
                  x={bar.x}
                  y={bar.downloadsY}
                  width={bar.w}
                  height={bar.downloadsH}
                  rx="2"
                  fill="#a78bfa"
                >
                  <title>
                    {`${formatDateLabel(data[index].date)} | Downloads: ${formatCurrency(data[index].downloads, currency)}`}
                  </title>
                </rect>
              )}

              {data[index].value > 0 && (index === data.length - 1 || index % xStride === 0) && (
                <text x={bar.x + bar.w / 2} y={bar.totalY - 6} textAnchor="middle" fontSize="10" fill="#a7bdd7">
                  {formatCurrency(data[index].value, currency)}
                </text>
              )}

              {(index % xStride === 0 || index === data.length - 1) && (
                <text
                  x={bar.x + bar.w / 2}
                  y={padding.top + chartHeight + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#7f97b5"
                >
                  {formatDateLabel(data[index].date)}
                </text>
              )}
            </g>
          ))}
        </svg>
      )}

      {data.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-[#9fb3cf]">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-[#38bdf8]" />
            Storage
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-[#34d399]" />
            Processamento
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-[#a78bfa]" />
            Downloads
          </span>
        </div>
      )}
    </div>
  );
}
