"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, Trash2, Map, ExternalLink, AlertCircle, Upload, Copy, Check } from "lucide-react";
import { getImages, deleteImage, getOGCServices, type ImageRecord, type OGCServices } from "@/lib/api";
import { cn, STATUS_IS_ACTIVE, formatDate } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";

const POLL_MS = 5000;

export default function DashboardPage() {
  const router = useRouter();
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ImageRecord | null>(null);
  const [ogc, setOgc] = useState<OGCServices | null>(null);
  const [ogcLoading, setOgcLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

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

  // Refresh selected image data when list updates
  useEffect(() => {
    if (selected) {
      const updated = images.find((img) => img.id === selected.id);
      if (updated) setSelected(updated);
    }
  }, [images]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (!confirm("Remover esta imagem e seus serviços publicados?")) return;
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

  const hasActive = images.some((img) => STATUS_IS_ACTIVE[img.status]);

  return (
    <div className="flex h-full">
      {/* List panel */}
      <div className="flex-1 flex flex-col min-w-0 px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {images.length} imagem{images.length !== 1 ? "ns" : ""} registrada{images.length !== 1 ? "s" : ""}
              {hasActive && <span className="ml-2 text-brand-500 animate-pulse">● atualizando…</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setLoading(true); fetchImages(); }}
              className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
              title="Atualizar"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            <button
              onClick={() => router.push("/upload")}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600"
            >
              <Upload className="w-4 h-4" />
              Novo Upload
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {!loading && images.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-4 text-gray-400">
            <Upload className="w-16 h-16 text-gray-200" />
            <div>
              <p className="font-medium text-gray-500">Nenhuma imagem ainda</p>
              <p className="text-sm mt-1">Faça o upload de uma imagem geoespacial para começar.</p>
            </div>
            <button
              onClick={() => router.push("/upload")}
              className="mt-2 px-5 py-2.5 rounded-lg bg-brand-500 text-white font-medium text-sm hover:bg-brand-600"
            >
              Ir para Upload
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {images.map((img) => (
              <div
                key={img.id}
                onClick={() => openDetail(img)}
                className={cn(
                  "flex items-center gap-4 p-4 bg-white border rounded-xl cursor-pointer transition-all",
                  selected?.id === img.id
                    ? "border-brand-400 shadow-sm ring-1 ring-brand-200"
                    : "border-gray-200 hover:border-gray-300 hover:shadow-sm"
                )}
              >
                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-800 truncate">{img.filename}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{formatDate(img.created_at)}</p>
                </div>

                {/* CRS */}
                {img.crs && (
                  <span className="hidden sm:block text-xs text-gray-500 font-mono bg-gray-50 px-2 py-1 rounded shrink-0">
                    {img.crs}
                  </span>
                )}

                {/* Status */}
                <StatusBadge status={img.status} />

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  {img.status === "published" && (
                    <button
                      onClick={() => router.push(`/map?layer=${img.layer_name}&imageId=${img.id}`)}
                      className="p-1.5 rounded-lg hover:bg-brand-50 text-brand-500"
                      title="Ver no Mapa"
                    >
                      <Map className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(img.id)}
                    disabled={deleting === img.id}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 disabled:opacity-40"
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

      {/* Detail panel */}
      {selected && (
        <aside className="w-80 shrink-0 border-l border-gray-200 bg-white flex flex-col overflow-y-auto">
          <div className="px-5 py-5 border-b border-gray-100">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-semibold text-gray-800 truncate">{selected.filename}</p>
                <p className="text-xs text-gray-400 mt-0.5">{formatDate(selected.created_at)}</p>
              </div>
              <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-600 shrink-0 text-lg leading-none">✕</button>
            </div>
            <div className="mt-3">
              <StatusBadge status={selected.status} />
            </div>
            {selected.error_message && (
              <div className="mt-3 p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                {selected.error_message}
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="px-5 py-4 border-b border-gray-100 space-y-3">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Metadados</h3>

            <MetaRow label="ID">
              <code className="text-xs bg-gray-100 px-1 py-0.5 rounded break-all">{selected.id}</code>
            </MetaRow>

            {selected.crs && (
              <MetaRow label="SRC / CRS">
                <span className="font-mono text-xs">{selected.crs}</span>
              </MetaRow>
            )}

            {selected.bbox && (
              <MetaRow label="Bounding Box">
                <span className="font-mono text-xs leading-relaxed">
                  {selected.bbox.minx.toFixed(4)}, {selected.bbox.miny.toFixed(4)}<br />
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

          {/* OGC Services */}
          {selected.status === "published" && (
            <div className="px-5 py-4 flex-1">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Serviços OGC</h3>

              {ogcLoading ? (
                <p className="text-sm text-gray-400">Carregando serviços…</p>
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

                  <button
                    onClick={() => router.push(`/map?layer=${selected.layer_name}&imageId=${selected.id}`)}
                    className="w-full mt-2 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600"
                  >
                    <Map className="w-4 h-4" />
                    Visualizar no Mapa
                  </button>
                </div>
              ) : (
                <p className="text-sm text-gray-400">Serviços não disponíveis.</p>
              )}
            </div>
          )}
        </aside>
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
      <code className="text-xs bg-gray-100 px-1 py-0.5 rounded break-all flex-1">{value}</code>
      <button onClick={copy} className="shrink-0 p-0.5 text-gray-400 hover:text-brand-500" title="Copiar">
        {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
      </button>
    </div>
  );
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <div className="text-sm text-gray-700">{children}</div>
    </div>
  );
}

function OGCService({ label, url, example, serviceUrl }: { label: string; url: string; example?: string; serviceUrl?: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-600 mb-1">{label}</p>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-1 text-xs text-brand-600 hover:underline break-all"
      >
        <ExternalLink className="w-3 h-3 shrink-0" />
        GetCapabilities
      </a>
      {example && (
        <a
          href={example}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 hover:underline mt-0.5 break-all"
        >
          <ExternalLink className="w-3 h-3 shrink-0" />
          GetMap exemplo
        </a>
      )}
      {serviceUrl && (
        <div className="mt-1.5">
          <p className="text-xs text-gray-400 mb-0.5">URL do serviço</p>
          <CopyField value={serviceUrl} />
        </div>
      )}
    </div>
  );
}
