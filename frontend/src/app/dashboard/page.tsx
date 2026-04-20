"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  RefreshCw,
  Trash2,
  Map,
  Download,
  Search,
  ExternalLink,
  AlertCircle,
  Upload,
  Copy,
  Check,
  Layers3,
  BarChart3,
  UserCircle2,
  Building2,
} from "lucide-react";
import {
  getImages,
  deleteImage,
  getOGCServices,
  getImageDownloadUrl,
  type ImageRecord,
  type ImageStatus,
  type OGCServices,
} from "@/lib/api";
import { cn, STATUS_IS_ACTIVE, formatDate } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";
import StorageMetrics from "@/components/metrics/StorageMetrics";
import CostMetrics from "@/components/metrics/CostMetrics";
import { getCurrentUser, getImageOwner } from "@/lib/auth";

const POLL_MS = 5000;

type DashboardTab = "layers" | "metrics";
type LayersScopeTab = "mine" | "organization";
type LayerStatusFilter = "all" | "published" | "processing" | "error";

const STATUS_PROGRESS: Record<ImageStatus, number | null> = {
  pending: 10,
  uploading: 22,
  uploaded: 38,
  processing: 62,
  processed: 82,
  publishing: 94,
  published: null,
  error: null,
};

const STATUS_STEP_INDEX: Record<ImageStatus, number | null> = {
  pending: 1,
  uploading: 2,
  uploaded: 3,
  processing: 4,
  processed: 5,
  publishing: 6,
  published: null,
  error: null,
};

export default function DashboardPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<DashboardTab>("layers");
  const [layersScope, setLayersScope] = useState<LayersScopeTab>("organization");
  const [layerStatusFilter, setLayerStatusFilter] = useState<LayerStatusFilter>("all");
  const [layerQuery, setLayerQuery] = useState("");
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ImageRecord | null>(null);
  const [ogc, setOgc] = useState<OGCServices | null>(null);
  const [ogcLoading, setOgcLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const downloadingRef = useRef<string | null>(null);
  const currentUserEmail = useMemo(() => getCurrentUser()?.email.trim().toLowerCase() ?? null, []);

  const fetchImages = useCallback(async () => {
    try {
      const data = await getImages();
      setImages(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao carregar imagens");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchImages();
    const id = setInterval(fetchImages, POLL_MS);
    return () => clearInterval(id);
  }, [fetchImages]);

  useEffect(() => {
    if (selected) {
      const updated = images.find((img) => img.id === selected.id);
      if (updated) setSelected(updated);
    }
  }, [images]); // eslint-disable-line react-hooks/exhaustive-deps

  const myImages = useMemo(() => {
    if (!currentUserEmail) return [] as ImageRecord[];
    return images.filter((image) => getImageOwner(image.id) === currentUserEmail);
  }, [images, currentUserEmail]);

  const scopeImages = useMemo(() => {
    return layersScope === "mine" ? myImages : images;
  }, [layersScope, myImages, images]);

  const statusFilteredImages = useMemo(() => {
    if (layerStatusFilter === "all") return scopeImages;
    return scopeImages.filter((image) => image.status === layerStatusFilter);
  }, [scopeImages, layerStatusFilter]);

  const visibleImages = useMemo(() => {
    const normalized = layerQuery.trim().toLowerCase();
    if (!normalized) return statusFilteredImages;
    return statusFilteredImages.filter((image) => {
      return (
        image.filename.toLowerCase().includes(normalized) ||
        (image.crs ?? "").toLowerCase().includes(normalized) ||
        image.status.toLowerCase().includes(normalized)
      );
    });
  }, [statusFilteredImages, layerQuery]);

  useEffect(() => {
    if (!selected) return;
    if (!visibleImages.some((img) => img.id === selected.id)) {
      setSelected(null);
    }
  }, [visibleImages, selected]);

  const openDetail = async (img: ImageRecord) => {
    setSelected(img);
    setOgc(null);
    if (img.status === "published") {
      setOgcLoading(true);
      try {
        const data = await getOGCServices(img.id);
        setOgc(data);
      } catch {
        // OGC not available yet
      } finally {
        setOgcLoading(false);
      }
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Remover esta imagem e seus servicos publicados?")) return;
    setDeleting(id);
    try {
      await deleteImage(id);
      setImages((prev) => prev.filter((img) => img.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Erro ao deletar");
    } finally {
      setDeleting(null);
    }
  };

  const handleDownloadRaw = async (img: ImageRecord) => {
    if (downloadingRef.current === img.id) return;
    downloadingRef.current = img.id;
    setDownloadingId(img.id);
    try {
      const data = await getImageDownloadUrl(img.id, "raw");
      // Single download dispatch: avoid popup + fallback strategy that can trigger
      // duplicate browser download attempts in some clients.
      const link = document.createElement("a");
      link.href = data.download_url;
      link.rel = "noopener noreferrer";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Erro ao gerar download");
    } finally {
      downloadingRef.current = null;
      setDownloadingId(null);
    }
  };

  const hasActive = visibleImages.some((img) => STATUS_IS_ACTIVE[img.status]);
  const dashboardSummary = useMemo(() => {
    if (activeTab === "metrics") {
      return `${images.length} ${images.length !== 1 ? "imagens" : "imagem"} registrada${
        images.length !== 1 ? "s" : ""
      } na organizacao`;
    }

    const base = `${visibleImages.length} ${visibleImages.length !== 1 ? "imagens" : "imagem"} registrada${
      visibleImages.length !== 1 ? "s" : ""
    }`;
    if (layersScope === "mine") {
      return `${base} de ${images.length} na organizacao`;
    }
    if (layerStatusFilter !== "all" || layerQuery.trim()) {
      return `${base} (filtro aplicado)`;
    }
    return `${base} na organizacao`;
  }, [activeTab, images.length, layerQuery, layerStatusFilter, layersScope, visibleImages.length]);

  return (
    <div className="h-full flex flex-col bg-[#0b1220]/70">
      <div className="px-6 py-5 border-b border-[#1f2d44] bg-[#0f1a2b]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#e2ecff]">Dashboard</h1>
            <p className="text-sm text-[#90a8c6] mt-0.5">
              {dashboardSummary}
              {hasActive && <span className="ml-2 text-[#38bdf8] animate-pulse">* atualizando...</span>}
            </p>
          </div>

          {activeTab === "layers" && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setLoading(true);
                  fetchImages();
                }}
                className="p-2 rounded-lg border border-[#2a3f58] hover:bg-[#14263d] text-[#9fb3cf]"
                title="Atualizar"
              >
                <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              </button>
              <button
                onClick={() => router.push("/upload")}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#1d4f7a] text-[#dff4ff] text-sm font-medium hover:bg-[#25608f]"
              >
                <Upload className="w-4 h-4" />
                Novo Upload
              </button>
            </div>
          )}
        </div>

        <div className="mt-4 inline-flex rounded-xl border border-[#2a3f58] bg-[#0f1e31] p-1">
          <button
            onClick={() => setActiveTab("layers")}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold",
              activeTab === "layers" ? "bg-[#13263d] text-[#dff4ff] shadow-sm" : "text-[#8ba3c3]"
            )}
          >
            <Layers3 className="w-4 h-4" />
            Camadas e Metadados
          </button>
          <button
            onClick={() => setActiveTab("metrics")}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold",
              activeTab === "metrics" ? "bg-[#13263d] text-[#dff4ff] shadow-sm" : "text-[#8ba3c3]"
            )}
          >
            <BarChart3 className="w-4 h-4" />
            Metricas de Storage e Custos
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {activeTab === "metrics" ? (
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
          <StorageMetrics />
          <CostMetrics />
        </div>
      ) : (
        <div className="flex flex-1 min-h-0">
          <div className="flex-1 min-w-0 px-6 py-6 overflow-y-auto">
            <div className="mb-4 rounded-xl border border-[#2a3f58] bg-[#0f1e31] p-3">
              <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr_1fr]">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-[#7f97b5] mb-1">
                    1. Escopo
                  </p>
                  <div className="inline-flex rounded-lg border border-[#2a3f58] bg-[#0c1a2c] p-1">
                    <button
                      onClick={() => setLayersScope("mine")}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold",
                        layersScope === "mine" ? "bg-[#13263d] text-[#dff4ff] shadow-sm" : "text-[#8ba3c3]"
                      )}
                    >
                      <UserCircle2 className="w-4 h-4" />
                      Minhas camadas
                      <span className="rounded-md bg-[#0c1727] px-1.5 py-0.5 text-[11px] text-[#9fd8ff]">
                        {myImages.length}
                      </span>
                    </button>
                    <button
                      onClick={() => setLayersScope("organization")}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold",
                        layersScope === "organization" ? "bg-[#13263d] text-[#dff4ff] shadow-sm" : "text-[#8ba3c3]"
                      )}
                    >
                      <Building2 className="w-4 h-4" />
                      Camadas da Organizacao
                      <span className="rounded-md bg-[#0c1727] px-1.5 py-0.5 text-[11px] text-[#9fd8ff]">
                        {images.length}
                      </span>
                    </button>
                  </div>
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-[#7f97b5] mb-1">
                    2. Status
                  </p>
                  <select
                    value={layerStatusFilter}
                    onChange={(event) => setLayerStatusFilter(event.target.value as LayerStatusFilter)}
                    className="w-full rounded-lg border border-[#2a3f58] bg-[#0c1727] px-3 py-2 text-sm text-[#dff4ff] outline-none focus:border-[#38bdf8]"
                  >
                    <option value="all">Todos</option>
                    <option value="published">Publicados</option>
                    <option value="processing">Em processamento</option>
                    <option value="error">Com erro</option>
                  </select>
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-[#7f97b5] mb-1">
                    3. Busca
                  </p>
                  <label className="relative block">
                    <Search className="absolute left-3 top-2.5 w-4 h-4 text-[#7f97b5]" />
                    <input
                      value={layerQuery}
                      onChange={(event) => setLayerQuery(event.target.value)}
                      placeholder="Nome, EPSG ou status"
                      className="w-full rounded-lg border border-[#2a3f58] bg-[#0c1727] py-2 pl-9 pr-3 text-sm text-[#dff4ff] outline-none focus:border-[#38bdf8]"
                    />
                  </label>
                </div>
              </div>
            </div>

            {!loading && visibleImages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center gap-4 text-[#7f97b5]">
                <Upload className="w-16 h-16 text-[#324861]" />
                <div>
                  <p className="font-medium text-[#b7c8df]">
                    {layersScope === "mine" ? "Nenhuma camada vinculada ao seu usuario" : "Nenhuma imagem ainda"}
                  </p>
                  <p className="text-sm mt-1">
                    {layersScope === "mine"
                      ? "Os novos uploads realizados por voce aparecerao nesta aba."
                      : "Faca o upload de uma imagem geoespacial para comecar."}
                  </p>
                </div>
                <button
                  onClick={() => router.push("/upload")}
                  className="mt-2 px-5 py-2.5 rounded-lg bg-[#1d4f7a] text-[#dff4ff] font-medium text-sm hover:bg-[#25608f]"
                >
                  Ir para Upload
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {visibleImages.map((img) => (
                  <div
                    key={img.id}
                    onClick={() => openDetail(img)}
                    className={cn(
                      "flex items-center gap-4 p-4 bg-[#101b2c] border rounded-xl cursor-pointer transition-all",
                      selected?.id === img.id
                        ? "border-[#2f597f] shadow-sm ring-1 ring-[#1f4369]"
                        : "border-[#2a3f58] hover:border-[#365473] hover:shadow-sm"
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[#dbe8fb] truncate">{img.filename}</p>
                      <p className="text-xs text-[#7f97b5] mt-0.5">{formatDate(img.created_at)}</p>
                      <ProcessingProgress status={img.status} className="mt-2 max-w-[440px]" />
                    </div>

                    {img.crs && (
                      <span className="hidden sm:block text-xs text-[#9fb3cf] font-mono bg-[#0c1727] px-2 py-1 rounded shrink-0">
                        {img.crs}
                      </span>
                    )}

                    <StatusBadge status={img.status} />

                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      {img.status === "published" && (
                        <button
                          onClick={() => router.push(`/map?layer=${img.layer_name}&imageId=${img.id}`)}
                          className="p-1.5 rounded-lg hover:bg-[#13263d] text-[#38bdf8]"
                          title="Ver no Mapa"
                        >
                          <Map className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(img.id)}
                        disabled={deleting === img.id}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-[#7f97b5] hover:text-red-400 disabled:opacity-40"
                        title="Excluir"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {selected && (
            <aside className="w-80 shrink-0 border-l border-[#1f2d44] bg-[#0f1a2b] flex flex-col overflow-y-auto">
              <div className="px-5 py-5 border-b border-[#1f2d44]">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-[#dbe8fb] truncate">{selected.filename}</p>
                    <p className="text-xs text-[#7f97b5] mt-0.5">{formatDate(selected.created_at)}</p>
                  </div>
                  <button
                    onClick={() => setSelected(null)}
                    className="text-[#7f97b5] hover:text-[#dbe8fb] shrink-0 text-lg leading-none"
                  >
                    x
                  </button>
                </div>
                <div className="mt-3">
                  <StatusBadge status={selected.status} />
                </div>
                <ProcessingProgress status={selected.status} className="mt-3" />
                {selected.error_message && (
                  <div className="mt-3 p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                    {selected.error_message}
                  </div>
                )}
              </div>

              <div className="px-5 py-4 border-b border-[#1f2d44] space-y-3">
                <h3 className="text-xs font-semibold text-[#8fa8c6] uppercase tracking-wider">Metadados</h3>

                <MetaRow label="ID">
                  <code className="text-xs bg-[#0c1727] px-1 py-0.5 rounded break-all">{selected.id}</code>
                </MetaRow>

                {selected.crs && (
                  <MetaRow label="SRC / CRS">
                    <span className="font-mono text-xs">{selected.crs}</span>
                  </MetaRow>
                )}

                {selected.bbox && (
                  <MetaRow label="Bounding Box">
                    <span className="font-mono text-xs leading-relaxed">
                      {selected.bbox.minx.toFixed(4)}, {selected.bbox.miny.toFixed(4)}
                      <br />
                      {selected.bbox.maxx.toFixed(4)}, {selected.bbox.maxy.toFixed(4)}
                    </span>
                  </MetaRow>
                )}

                {selected.layer_name && (
                  <MetaRow label="Layer">
                    <span className="font-mono text-xs">{selected.layer_name}</span>
                  </MetaRow>
                )}
              </div>

              {selected.status === "published" && (
                <div className="px-5 py-4 flex-1">
                  <h3 className="text-xs font-semibold text-[#8fa8c6] uppercase tracking-wider mb-3">
                    Servicos OGC
                  </h3>

                  {ogcLoading ? (
                    <p className="text-sm text-[#7f97b5]">Carregando servicos...</p>
                  ) : ogc ? (
                    <div className="space-y-4">
                      <OGCService
                        label="WMS"
                        url={ogc.services.wms.getcapabilities}
                        example={ogc.services.wms.getmap_example}
                        serviceUrl={ogc.services.wms.url}
                      />
                      <OGCService
                        label="WMTS"
                        url={ogc.services.wmts.getcapabilities}
                        serviceUrl={ogc.services.wmts.url}
                      />
                      <OGCService
                        label="WCS"
                        url={ogc.services.wcs.getcapabilities}
                        serviceUrl={ogc.services.wcs.url}
                      />

                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <button
                          onClick={() =>
                            router.push(`/map?layer=${selected.layer_name}&imageId=${selected.id}`)
                          }
                          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#1d4f7a] text-[#dff4ff] text-sm font-medium hover:bg-[#25608f]"
                        >
                          <Map className="w-4 h-4" />
                          Visualizar no Mapa
                        </button>
                        <button
                          onClick={() => handleDownloadRaw(selected)}
                          disabled={downloadingId === selected.id}
                          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-[#2a3f58] bg-[#13263d] text-[#dff4ff] text-sm font-medium hover:bg-[#1a324f] disabled:opacity-60"
                        >
                          <Download className="w-4 h-4" />
                          {downloadingId === selected.id ? "Gerando..." : "Download dado"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-[#7f97b5]">Servicos nao disponiveis.</p>
                  )}
                </div>
              )}
            </aside>
          )}
        </div>
      )}
    </div>
  );
}

function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="flex items-start gap-1">
      <code className="text-xs bg-white text-black border border-slate-300 px-1 py-0.5 rounded break-all flex-1">
        {value}
      </code>
      <button onClick={copy} className="shrink-0 p-0.5 text-slate-700 hover:text-black" title="Copiar">
        {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
      </button>
    </div>
  );
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-[#8fa8c6] mb-0.5">{label}</p>
      <div className="text-sm text-[#dbe8fb]">{children}</div>
    </div>
  );
}

function OGCService({
  label,
  url,
  example,
  serviceUrl,
}: {
  label: string;
  url: string;
  example?: string;
  serviceUrl?: string;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-[#9fb3cf] mb-1">{label}</p>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-1 text-xs text-[#38bdf8] hover:underline break-all"
      >
        <ExternalLink className="w-3 h-3 shrink-0" />
        GetCapabilities
      </a>
      {example && (
        <a
          href={example}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-xs text-[#7f97b5] hover:text-[#dbe8fb] hover:underline mt-0.5 break-all"
        >
          <ExternalLink className="w-3 h-3 shrink-0" />
          GetMap exemplo
        </a>
      )}
      {serviceUrl && (
        <div className="mt-1.5">
          <p className="text-xs text-[#8fa8c6] mb-0.5">URL do servico</p>
          <CopyField value={serviceUrl} />
        </div>
      )}
    </div>
  );
}

function ProcessingProgress({
  status,
  className,
}: {
  status: ImageStatus;
  className?: string;
}) {
  const progress = STATUS_PROGRESS[status];
  const step = STATUS_STEP_INDEX[status];

  if (progress === null || step === null) return null;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-[11px] text-[#8fa8c6]">
        <span>Progresso do processamento</span>
        <span>{progress}%</span>
      </div>
      <div className="h-2 rounded-full bg-[#0c1727] border border-[#20344d] overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#1fa3ff] to-[#4dd4ff] transition-all duration-500 animate-pulse"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-[11px] text-[#6e86a8]">Etapa {step}/6 em andamento</p>
    </div>
  );
}
