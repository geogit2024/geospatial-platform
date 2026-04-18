"use client";

import { FormEvent, useEffect, useState } from "react";
import { getCostMetrics, simulateCostMetrics, type CostMetrics } from "@/lib/api";
import KpiCard from "./KpiCard";
import CostChart from "./CostChart";

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(value);
}

export default function CostMetricsSection() {
  const [windowDays, setWindowDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CostMetrics | null>(null);

  const [extraGb, setExtraGb] = useState("10");
  const [extraProcesses, setExtraProcesses] = useState("0");
  const [extraDownloads, setExtraDownloads] = useState("0");
  const [simulating, setSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState<null | {
    extra_total: number;
    new_estimated_total: number;
  }>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        const response = await getCostMetrics(windowDays);
        if (active) {
          setData(response);
          setSimulationResult(null);
          setSimulationError(null);
        }
      } catch (err: unknown) {
        if (active) {
          setData(null);
          setError(err instanceof Error ? err.message : "Falha ao carregar metricas de custo.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [windowDays]);

  const runSimulation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) return;

    setSimulating(true);
    setSimulationError(null);

    try {
      const response = await simulateCostMetrics({
        window_days: windowDays,
        extra_gb: Number(extraGb) || 0,
        extra_processes: Number(extraProcesses) || 0,
        extra_downloads: Number(extraDownloads) || 0,
      });
      setSimulationResult({
        extra_total: response.extra_total,
        new_estimated_total: response.new_estimated_total,
      });
    } catch (err: unknown) {
      setSimulationError(err instanceof Error ? err.message : "Falha ao simular custo.");
    } finally {
      setSimulating(false);
    }
  };

  const currency = data?.currency ?? "BRL";

  return (
    <section className="rounded-2xl border border-[#24344b] bg-[#0e1829]/95 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-bold text-[#e2ecff]">Custos e Cobranca</h2>
          {data && (
            <p className={`mt-1 text-[11px] ${data.cost_source_is_real ? "text-emerald-300" : "text-amber-300"}`}>
              Fonte:{" "}
              {data.cost_source_is_real
                ? "GCP Billing Export (BigQuery)"
                : "Configurada (nao-real)"}{" "}
              {data.cost_source_table ? `- ${data.cost_source_table}` : ""}
            </p>
          )}
        </div>
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
        <KpiCard
          title="Custo mensal"
          value={loading || !data ? "..." : formatCurrency(data.estimated_total, currency)}
          tone="green"
        />
        <KpiCard
          title="Projecao 30 dias"
          value={loading || !data ? "..." : formatCurrency(data.projection_30_days, currency)}
          tone="blue"
        />
        <KpiCard
          title="Custo por GB"
          value={loading || !data ? "..." : formatCurrency(data.cost_per_gb, currency)}
          subtitle="por GB/mes"
        />
        <KpiCard
          title="Processamento"
          value={loading || !data ? "..." : formatCurrency(data.processing_cost, currency)}
          subtitle="janela selecionada"
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <CostChart data={data?.cost_timeseries ?? []} currency={currency} />

        <form onSubmit={runSimulation} className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4 shadow-sm">
          <p className="text-sm font-semibold text-[#dbe8fb]">Simulador SaaS</p>
          <p className="mt-1 text-xs text-[#7f97b5]">Simule impacto de uso adicional no custo mensal.</p>

          <div className="mt-3 space-y-2">
            <label className="block text-xs text-[#9fb3cf]">
              + GB
              <input
                type="number"
                min="0"
                step="0.1"
                value={extraGb}
                onChange={(e) => setExtraGb(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2 text-sm text-[#dbe8fb]"
              />
            </label>

            <label className="block text-xs text-[#9fb3cf]">
              + Processamentos
              <input
                type="number"
                min="0"
                step="1"
                value={extraProcesses}
                onChange={(e) => setExtraProcesses(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2 text-sm text-[#dbe8fb]"
              />
            </label>

            <label className="block text-xs text-[#9fb3cf]">
              + Downloads
              <input
                type="number"
                min="0"
                step="1"
                value={extraDownloads}
                onChange={(e) => setExtraDownloads(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2 text-sm text-[#dbe8fb]"
              />
            </label>
          </div>

          <button
            type="submit"
            disabled={simulating || !data}
            className="mt-3 w-full rounded-lg bg-[#1d4f7a] px-4 py-2 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {simulating ? "Simulando..." : "Simular custo"}
          </button>

          {simulationError && <p className="mt-2 text-xs text-red-600">{simulationError}</p>}

          {simulationResult && (
            <div className="mt-3 rounded-lg bg-[#0f2034] p-3 text-xs text-[#9fb3cf]">
              <p>Custo adicional: <strong>{formatCurrency(simulationResult.extra_total, currency)}</strong></p>
              <p className="mt-1">Novo total estimado: <strong>{formatCurrency(simulationResult.new_estimated_total, currency)}</strong></p>
            </div>
          )}
        </form>
      </div>
    </section>
  );
}
