"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";

import {
  cleanupUploadCostEstimateSessions,
  getUploadCostEstimateAudit,
  type UploadCostEstimateAuditResponse,
} from "@/lib/api";
import KpiCard from "./KpiCard";

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR");
}

export default function UploadCostEstimateMetrics() {
  const [windowDays, setWindowDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<UploadCostEstimateAuditResponse | null>(null);
  const [runningCleanup, setRunningCleanup] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getUploadCostEstimateAudit(windowDays, undefined, 20);
      setData(payload);
    } catch (err: unknown) {
      setData(null);
      setError(err instanceof Error ? err.message : "Falha ao carregar auditoria.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await getUploadCostEstimateAudit(windowDays, undefined, 20);
        if (!active) return;
        setData(payload);
      } catch (err: unknown) {
        if (!active) return;
        setData(null);
        setError(err instanceof Error ? err.message : "Falha ao carregar auditoria.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [windowDays]);

  const cleanupExpired = async () => {
    setRunningCleanup(true);
    setCleanupMessage(null);
    try {
      const response = await cleanupUploadCostEstimateSessions({ limit: 500 });
      setCleanupMessage(
        response.deleted_count > 0
          ? `${response.deleted_count} sessoes expiradas removidas.`
          : "Nenhuma sessao expirada para remover."
      );
      await load();
    } catch (err: unknown) {
      setCleanupMessage(err instanceof Error ? err.message : "Falha na limpeza.");
    } finally {
      setRunningCleanup(false);
    }
  };

  const currency = data?.accepted_averages.currency ?? "BRL";
  const totals = data?.totals;
  const rates = data?.rates;

  return (
    <section className="rounded-2xl border border-[#24344b] bg-[#0e1829]/95 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-bold text-[#e2ecff]">Auditoria de Estimativas de Upload</h2>
          <p className="mt-1 text-[11px] text-[#8ba3c3]">
            Monitoramento de aceite, conversao em upload e limpeza de sessoes expiradas.
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-lg border border-[#2a3f58] bg-[#0f1e31] px-3 py-1.5 text-xs font-semibold text-[#dff4ff] hover:bg-[#13263d] disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Atualizar
          </button>
          <button
            onClick={cleanupExpired}
            disabled={runningCleanup}
            className="inline-flex items-center gap-1 rounded-lg border border-[#64462a] bg-[#3c2814] px-3 py-1.5 text-xs font-semibold text-[#ffd6b0] hover:bg-[#51351a] disabled:opacity-60"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {runningCleanup ? "Limpando..." : "Limpar expiradas"}
          </button>
        </div>
      </div>

      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {cleanupMessage && (
        <p className="mb-3 rounded-lg bg-[#102237] px-3 py-2 text-xs text-[#b7d7ff]">{cleanupMessage}</p>
      )}

      <div className="grid gap-3 md:grid-cols-4">
        <KpiCard title="Sessoes na janela" value={loading || !totals ? "..." : String(totals.sessions)} tone="blue" />
        <KpiCard
          title="Taxa de aceite"
          value={loading || !rates ? "..." : `${rates.acceptance_rate_pct.toFixed(2)}%`}
          tone="green"
        />
        <KpiCard
          title="Conversao em upload"
          value={loading || !rates ? "..." : `${rates.conversion_to_upload_pct.toFixed(2)}%`}
        />
        <KpiCard
          title="Expiradas acumuladas"
          value={loading || !totals ? "..." : String(totals.expired_total)}
          subtitle="cleanup recomendado"
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4">
          <p className="text-sm font-semibold text-[#dbe8fb]">Resumo financeiro de aceites</p>
          <p className="mt-1 text-xs text-[#7f97b5]">Media das estimativas aceitas/consumidas na janela.</p>
          <div className="mt-3 space-y-2 text-sm">
            <p className="text-[#9fb3cf]">
              Primeiro mes medio:{" "}
              <strong className="text-[#dff4ff]">
                {loading || !data
                  ? "..."
                  : formatCurrency(data.accepted_averages.first_month_total, currency)}
              </strong>
            </p>
            <p className="text-[#9fb3cf]">
              Recorrente mensal medio:{" "}
              <strong className="text-[#dff4ff]">
                {loading || !data
                  ? "..."
                  : formatCurrency(data.accepted_averages.recurring_monthly_total, currency)}
              </strong>
            </p>
          </div>

          <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-[#7f97b5]">Status</p>
          <div className="mt-2 space-y-1 text-xs">
            {(data?.status_breakdown ?? []).map((item) => (
              <div
                key={item.status}
                className="flex items-center justify-between rounded-md border border-[#24344b] bg-[#0f1a2b] px-2 py-1.5"
              >
                <span className="text-[#9fb3cf]">{item.status}</span>
                <span className="font-semibold text-[#dff4ff]">{item.count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] p-4">
          <p className="text-sm font-semibold text-[#dbe8fb]">Ultimas sessoes</p>
          <p className="mt-1 text-xs text-[#7f97b5]">Top 20 sessoes para auditoria operacional.</p>
          <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-[#24344b]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0f1a2b] text-[#9fb3cf]">
                <tr>
                  <th className="px-2 py-2 text-left font-semibold">Arquivo</th>
                  <th className="px-2 py-2 text-left font-semibold">Status</th>
                  <th className="px-2 py-2 text-right font-semibold">1o mes</th>
                  <th className="px-2 py-2 text-left font-semibold">Criado em</th>
                </tr>
              </thead>
              <tbody>
                {(data?.recent_sessions ?? []).map((item) => (
                  <tr key={item.session_id} className="border-t border-[#24344b] text-[#dbe8fb]">
                    <td className="px-2 py-2">
                      <p className="max-w-[220px] truncate">{item.filename}</p>
                      <p className="text-[10px] text-[#7f97b5]">
                        {item.asset_type} · {item.size_gb.toFixed(2)} GB
                      </p>
                    </td>
                    <td className="px-2 py-2">
                      <span className="rounded bg-[#0c1727] px-1.5 py-0.5">{item.status}</span>
                    </td>
                    <td className="px-2 py-2 text-right font-semibold">
                      {formatCurrency(item.first_month_total, item.currency)}
                    </td>
                    <td className="px-2 py-2 text-[#9fb3cf]">{formatDateTime(item.created_at)}</td>
                  </tr>
                ))}
                {!loading && (data?.recent_sessions.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={4} className="px-2 py-4 text-center text-[#7f97b5]">
                      Sem sessoes na janela selecionada.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
