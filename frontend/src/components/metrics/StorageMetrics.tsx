"use client";

import { useEffect, useMemo, useState } from "react";
import { getStorageMetrics, type DistributionByType, type StorageMetrics } from "@/lib/api";
import KpiCard from "./KpiCard";
import UsageChart from "./UsageChart";

function formatNumber(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function formatGb(value: number) {
  return `${value.toFixed(2)} GB`;
}

function DistributionDonut({ data }: { data: DistributionByType[] }) {
  if (!data.length) {
    return <p className="text-sm text-[#7f97b5]">Sem distribuicao por tipo.</p>;
  }

  const total = data.reduce((acc, item) => acc + item.count, 0) || 1;
  const palette = ["#00E5FF", "#FF4D6D", "#7C4DFF", "#FFB300", "#00E676", "#FF6D00"];
  let cursor = 0;

  const segments = data.map((item, index) => {
    const pct = (item.count / total) * 100;
    const color = palette[index % palette.length];
    const part = `${color} ${cursor.toFixed(2)}% ${(cursor + pct).toFixed(2)}%`;
    cursor += pct;
    return { part, color, label: item.type, pct };
  });

  const gradient = `conic-gradient(${segments.map((s) => s.part).join(",")})`;

  return (
    <div className="grid gap-3 sm:grid-cols-[130px_1fr] sm:items-center">
      <div
        className="mx-auto h-28 w-28 rounded-full border border-[#2a3f58]"
        style={{ background: gradient }}
      />
      <div className="space-y-1 text-xs text-[#9fb3cf]">
        {segments.map((segment) => (
          <div key={segment.label} className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: segment.color }} />
              {segment.label}
            </span>
            <span>{segment.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function StorageMetricsSection() {
  const [windowDays, setWindowDays] = useState(30);
  const [accessType, setAccessType] = useState<"all" | "download" | "ogc">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<StorageMetrics | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await getStorageMetrics(windowDays, undefined, accessType);
        if (active) setData(response);
      } catch (err: unknown) {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar metricas de uso.");
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [windowDays, accessType]);

  const growthLabel = useMemo(() => {
    if (!data) return "0%";
    const signal = data.growth_window_pct > 0 ? "+" : "";
    return `${signal}${data.growth_window_pct.toFixed(2)}%`;
  }, [data]);

  return (
    <section className="rounded-2xl border border-[#24344b] bg-[#0e1829]/95 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-bold text-[#e2ecff]">Uso do Sistema</h2>
        <div className="inline-flex rounded-lg border border-[#2a3f58] bg-[#0f1e31] p-1 text-xs">
          {[7, 30].map((days) => (
            <button
              key={days}
              onClick={() => setWindowDays(days)}
              className={`rounded-md px-2.5 py-1 font-semibold ${
                windowDays === days ? "bg-[#1d4f7a] text-[#dff4ff]" : "text-[#96abc7]"
              }`}
            >
              {days}d
            </button>
          ))}
        </div>
      </div>

      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="grid gap-3 md:grid-cols-4">
        <KpiCard title="Arquivos" value={loading || !data ? "..." : formatNumber(data.total_files)} tone="blue" />
        <KpiCard title="Armazenamento" value={loading || !data ? "..." : formatGb(data.total_size_gb)} tone="blue" />
        <KpiCard title="Media por arquivo" value={loading || !data ? "..." : `${data.avg_size_mb.toFixed(1)} MB`} />
        <KpiCard title="Crescimento" value={loading || !data ? "..." : growthLabel} tone={data && data.growth_window_pct > 0 ? "green" : "slate"} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <UsageChart data={data?.usage_timeseries ?? []} />
        <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
          <p className="text-sm font-semibold text-[#dbe8fb]">Distribuicao por tipo</p>
          <div className="mt-3">
            <DistributionDonut data={data?.distribution_by_type ?? []} />
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
          <p className="text-sm font-semibold text-[#dbe8fb]">Top 5 arquivos mais pesados</p>
          <div className="mt-3 space-y-2 text-sm">
            {(data?.top_files ?? []).map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-2 border-b border-[#1d2b3e] pb-2">
                <span className="truncate text-[#9fb3cf]">{item.filename}</span>
                <span className="font-semibold text-[#dbe8fb]">{item.size_mb.toFixed(1)} MB</span>
              </div>
            ))}
            {!loading && !(data?.top_files.length) && <p className="text-[#7f97b5]">Sem dados de tamanho.</p>}
          </div>
        </div>

        <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-[#dbe8fb]">Mais acessados</p>
            <div className="inline-flex rounded-md border border-[#2a3f58] bg-[#0f1e31] p-0.5 text-[11px]">
              {[
                { key: "all", label: "Todos" },
                { key: "download", label: "Download" },
                { key: "ogc", label: "OGC" },
              ].map((item) => (
                <button
                  key={item.key}
                  onClick={() => setAccessType(item.key as "all" | "download" | "ogc")}
                  className={`rounded px-2 py-1 font-semibold ${
                    accessType === item.key ? "bg-[#1d4f7a] text-[#dff4ff]" : "text-[#96abc7]"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-3 space-y-2 text-sm">
            {(data?.top_accessed ?? []).map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3 border-b border-[#1d2b3e] pb-2">
                <span className="min-w-0 truncate text-[#9fb3cf]">{item.filename}</span>
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <span className="rounded bg-[#133554] px-1.5 py-0.5 text-[11px] font-semibold text-[#9fd9ff]">
                    D {item.download_accesses}
                  </span>
                  <span className="rounded bg-[#13463a] px-1.5 py-0.5 text-[11px] font-semibold text-[#8ff4c9]">
                    OGC {item.ogc_accesses}
                  </span>
                  <span className="font-semibold text-[#dbe8fb]">{item.accesses}</span>
                </div>
              </div>
            ))}
            {!loading && !(data?.top_accessed.length) && (
              <p className="text-[#7f97b5]">
                {accessType === "ogc" ? "Sem consumo OGC na janela selecionada." : "Sem logs de acesso ainda."}
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
