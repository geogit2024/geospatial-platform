"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileImage, Loader2, Upload, XCircle } from "lucide-react";

import { registerImageOwner } from "@/lib/auth";
import {
  acceptUploadCostEstimate,
  confirmUpload,
  getUploadCostEstimateConfig,
  recalculateUploadCostEstimate,
  requestSignedUrl,
  startUploadCostEstimate,
  type UploadCostEstimate,
  uploadFileDirect,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Step = "idle" | "signing" | "uploading" | "confirming" | "done" | "error";

const ACCEPTED = [
  ".tif",
  ".tiff",
  ".geotiff",
  ".jp2",
  ".img",
  ".jpg",
  ".jpeg",
  ".zip",
  ".kml",
  ".geojson",
  ".json",
];
const ACCEPT_MIME =
  "image/tiff,image/jpeg,application/zip,application/vnd.google-earth.kml+xml,application/geo+json,.tif,.tiff,.geotiff,.jp2,.img,.jpg,.jpeg,.zip,.kml,.geojson,.json";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadingRef = useRef(false);
  const estimateRunRef = useRef(0);

  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [progress, setProgress] = useState(0);
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const [estimateEnabled, setEstimateEnabled] = useState(false);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimateSessionId, setEstimateSessionId] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<UploadCostEstimate | null>(null);
  const [expectedMonthlyDownloads, setExpectedMonthlyDownloads] = useState(100);
  const [avgDownloadSizeRatio, setAvgDownloadSizeRatio] = useState(0.35);
  const [recalculatingEstimate, setRecalculatingEstimate] = useState(false);

  const formatCurrency = useCallback((value: number, currency: string) => {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }, []);

  const resetEstimateState = useCallback(() => {
    setEstimateEnabled(false);
    setEstimateLoading(false);
    setEstimateError(null);
    setEstimateSessionId(null);
    setEstimate(null);
    setExpectedMonthlyDownloads(100);
    setAvgDownloadSizeRatio(0.35);
    setRecalculatingEstimate(false);
  }, []);

  const loadEstimateForFile = useCallback(
    async (selectedFile: File) => {
      const runId = ++estimateRunRef.current;
      setEstimateLoading(true);
      setEstimateError(null);
      setEstimateEnabled(false);
      setEstimate(null);
      setEstimateSessionId(null);

      try {
        const config = await getUploadCostEstimateConfig();
        if (runId !== estimateRunRef.current) return;

        if (!config.is_enabled) {
          setEstimateEnabled(false);
          return;
        }

        setEstimateEnabled(true);
        const started = await startUploadCostEstimate({
          filename: selectedFile.name,
          sizeBytes: selectedFile.size,
          contentType: selectedFile.type || "application/octet-stream",
        });
        if (runId !== estimateRunRef.current) return;

        setEstimateSessionId(started.session_id);
        setEstimate(started.estimate);
        setExpectedMonthlyDownloads(
          Number(started.estimate.assumptions_used.expected_monthly_downloads || 0)
        );
        setAvgDownloadSizeRatio(Number(started.estimate.assumptions_used.avg_download_size_ratio || 0.35));
      } catch (e: unknown) {
        if (runId !== estimateRunRef.current) return;
        const message = e instanceof Error ? e.message : "Erro desconhecido";

        if (message.startsWith("403")) {
          setEstimateEnabled(false);
          setEstimateError(null);
        } else {
          setEstimateError(`Falha ao calcular previsao de custo: ${message}`);
        }
      } finally {
        if (runId === estimateRunRef.current) {
          setEstimateLoading(false);
        }
      }
    },
    []
  );

  const handleFile = useCallback(
    (selectedFile: File) => {
      const ext = "." + selectedFile.name.split(".").pop()!.toLowerCase();
      if (!ACCEPTED.includes(ext)) {
        setError(`Formato nao suportado: ${ext}. Use: ${ACCEPTED.join(", ")}`);
        return;
      }

      setFile(selectedFile);
      setError(null);
      setStep("idle");
      setProgress(0);
      setImageId(null);
      void loadEstimateForFile(selectedFile);
    },
    [loadEstimateForFile]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) handleFile(dropped);
    },
    [handleFile]
  );

  const recalculateEstimate = async () => {
    if (!estimateSessionId || recalculatingEstimate) return;
    setRecalculatingEstimate(true);
    setEstimateError(null);

    try {
      const response = await recalculateUploadCostEstimate({
        sessionId: estimateSessionId,
        expectedMonthlyDownloads: Math.max(0, Math.floor(expectedMonthlyDownloads)),
        avgDownloadSizeRatio: Math.max(0.01, Math.min(2, avgDownloadSizeRatio)),
      });
      setEstimate(response.estimate);
    } catch (e: unknown) {
      setEstimateError(e instanceof Error ? e.message : "Falha ao recalcular previsao de custo.");
    } finally {
      setRecalculatingEstimate(false);
    }
  };

  const startUpload = async () => {
    if (!file || uploadingRef.current) return;
    uploadingRef.current = true;
    setError(null);
    setStep("signing");

    try {
      if (estimateSessionId && estimateEnabled) {
        const accepted = await acceptUploadCostEstimate({
          sessionId: estimateSessionId,
          expectedMonthlyDownloads: Math.max(0, Math.floor(expectedMonthlyDownloads)),
          avgDownloadSizeRatio: Math.max(0.01, Math.min(2, avgDownloadSizeRatio)),
        });
        setEstimate(accepted.estimate);
      }

      const { image_id, upload_url, content_type } = await requestSignedUrl(
        file.name,
        file.type || "application/octet-stream",
        file.size
      );
      setImageId(image_id);

      setStep("uploading");
      await uploadFileDirect(upload_url, file, setProgress, content_type);

      setStep("confirming");
      await confirmUpload(image_id, estimateSessionId || undefined);
      registerImageOwner(image_id);
      setStep("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
      setStep("error");
    } finally {
      uploadingRef.current = false;
    }
  };

  const canStartUpload = Boolean(file) && ["idle", "error"].includes(step) && !estimateLoading;

  const STEP_LABEL: Record<Step, string> = {
    idle: "",
    signing: "Gerando URL segura...",
    uploading: `Enviando ${progress}%`,
    confirming: "Enfileirando processamento...",
    done: "Upload concluido! Processamento iniciado.",
    error: "",
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 text-[#dbe8fb]">
      <h1 className="text-2xl font-bold mb-1 text-[#e2ecff]">Upload de Imagem</h1>
      <p className="text-[#9fb3cf] mb-8">
        Formatos suportados: GeoTIFF, JP2, IMG, JPG/JPEG, SHP (.zip), KML e GeoJSON. Upload direto para o
        storage - a API nao transita os bytes.
      </p>

      <div
        className={cn(
          "border-2 border-dashed rounded-xl p-10 flex flex-col items-center gap-4 cursor-pointer transition-colors",
          dragging ? "border-[#38bdf8] bg-[#13263d]" : "border-[#2a3f58] hover:border-[#38bdf8] bg-[#101b2c]"
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_MIME}
          className="hidden"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />

        {file ? (
          <>
            <FileImage className="w-12 h-12 text-[#38bdf8]" />
            <div className="text-center">
              <p className="font-semibold text-[#dbe8fb]">{file.name}</p>
              <p className="text-sm text-[#9fb3cf]">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </>
        ) : (
          <>
            <Upload className="w-12 h-12 text-[#7f97b5]" />
            <div className="text-center">
              <p className="font-semibold text-[#dbe8fb]">Arraste e solte ou clique para selecionar</p>
              <p className="text-sm text-[#9fb3cf] mt-1">{ACCEPTED.join("  ")}</p>
            </div>
          </>
        )}
      </div>

      {file && (
        <div className="mt-5 rounded-xl border border-[#2a3f58] bg-[#0f1d30] p-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold text-[#dfeeff]">Previsao de custo antes do processamento</h2>
            {estimateLoading && (
              <span className="inline-flex items-center gap-1 text-xs text-[#9fb3cf]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Calculando...
              </span>
            )}
          </div>

          {!estimateLoading && !estimateEnabled && (
            <p className="mt-2 text-xs text-[#91a8c8]">
              Previsao de custo indisponivel para o tenant atual. O upload segue funcionando normalmente.
            </p>
          )}

          {!estimateLoading && estimate && (
            <>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-[#13263d] p-3">
                  <p className="text-[11px] uppercase tracking-wide text-[#84a2c8]">Primeiro mes (provavel)</p>
                  <p className="mt-1 text-lg font-semibold text-[#e6f3ff]">
                    {formatCurrency(estimate.breakdown.first_month_total, estimate.currency)}
                  </p>
                  <p className="mt-1 text-[11px] text-[#9fb3cf]">
                    Faixa: {formatCurrency(estimate.breakdown.first_month_range.minimum, estimate.currency)} a{" "}
                    {formatCurrency(estimate.breakdown.first_month_range.maximum, estimate.currency)}
                  </p>
                </div>
                <div className="rounded-lg bg-[#13263d] p-3">
                  <p className="text-[11px] uppercase tracking-wide text-[#84a2c8]">Recorrente mensal</p>
                  <p className="mt-1 text-lg font-semibold text-[#e6f3ff]">
                    {formatCurrency(estimate.breakdown.recurring_monthly_total, estimate.currency)}
                  </p>
                  <p className="mt-1 text-[11px] text-[#9fb3cf]">
                    Storage {formatCurrency(estimate.breakdown.storage_monthly, estimate.currency)} + publicacao{" "}
                    {formatCurrency(estimate.breakdown.publication_monthly, estimate.currency)}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label className="text-xs text-[#9fb3cf]">
                  Downloads/mes esperados
                  <input
                    type="number"
                    min={0}
                    step={10}
                    value={expectedMonthlyDownloads}
                    onChange={(e) =>
                      setExpectedMonthlyDownloads(Math.max(0, Number(e.target.value || 0)))
                    }
                    className="mt-1 w-full rounded-md border border-[#2a3f58] bg-[#0c1727] px-2 py-1.5 text-sm text-[#dbe8fb] outline-none focus:border-[#38bdf8]"
                  />
                </label>

                <label className="text-xs text-[#9fb3cf]">
                  Razao media de download
                  <input
                    type="number"
                    min={0.01}
                    max={2}
                    step={0.01}
                    value={avgDownloadSizeRatio}
                    onChange={(e) =>
                      setAvgDownloadSizeRatio(Number(e.target.value || 0.35))
                    }
                    className="mt-1 w-full rounded-md border border-[#2a3f58] bg-[#0c1727] px-2 py-1.5 text-sm text-[#dbe8fb] outline-none focus:border-[#38bdf8]"
                  />
                </label>

                <div className="flex items-end">
                  <button
                    onClick={recalculateEstimate}
                    disabled={recalculatingEstimate || !estimateSessionId}
                    className={cn(
                      "w-full rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      !recalculatingEstimate && estimateSessionId
                        ? "bg-[#1d4f7a] text-[#dff4ff] hover:bg-[#25608f]"
                        : "bg-[#1d2b3e] text-[#7f97b5] cursor-not-allowed"
                    )}
                  >
                    {recalculatingEstimate ? "Recalculando..." : "Recalcular previsao"}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {step === "uploading" && (
        <div className="mt-4 w-full bg-[#1d2b3e] rounded-full h-2">
          <div className="bg-[#38bdf8] h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>
      )}

      {step !== "idle" && step !== "error" && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          {step === "done" ? (
            <CheckCircle2 className="w-4 h-4 text-green-400" />
          ) : (
            <Loader2 className="w-4 h-4 text-[#38bdf8] animate-spin" />
          )}
          <span className={step === "done" ? "text-green-400 font-medium" : "text-[#9fb3cf]"}>{STEP_LABEL[step]}</span>
        </div>
      )}

      {estimateError && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {estimateError}
        </div>
      )}

      {error && (
        <div className="mt-4 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <div className="mt-6 flex gap-3">
        {step !== "done" ? (
          <button
            onClick={startUpload}
            disabled={!canStartUpload}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm transition-colors",
              canStartUpload
                ? "bg-[#1d4f7a] text-[#dff4ff] hover:bg-[#25608f]"
                : "bg-[#1d2b3e] text-[#7f97b5] cursor-not-allowed"
            )}
          >
            <Upload className="w-4 h-4" />
            {estimateLoading ? "Calculando previsao..." : "Iniciar Upload e Processamento"}
          </button>
        ) : (
          <>
            <button
              onClick={() => router.push("/dashboard")}
              className="px-5 py-2.5 rounded-lg bg-[#1d4f7a] text-[#dff4ff] font-medium text-sm hover:bg-[#25608f]"
            >
              Ver no Dashboard
            </button>
            <button
              onClick={() => {
                setFile(null);
                setStep("idle");
                setProgress(0);
                setImageId(null);
                resetEstimateState();
              }}
              className="px-5 py-2.5 rounded-lg border border-[#2a3f58] text-[#9fb3cf] font-medium text-sm hover:bg-[#122033]"
            >
              Novo Upload
            </button>
          </>
        )}
      </div>

      {imageId && step === "done" && (
        <p className="mt-3 text-xs text-[#8aa2c4]">
          ID da imagem: <code className="bg-[#0c1727] px-1 py-0.5 rounded">{imageId}</code>
        </p>
      )}
    </div>
  );
}
