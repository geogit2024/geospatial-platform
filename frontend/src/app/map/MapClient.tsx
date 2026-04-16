"use client";
import { useEffect, useRef, useState } from "react";
import { getImages, type ImageRecord } from "@/lib/api";
import { cn, STATUS_LABEL } from "@/lib/utils";
import StatusBadge from "@/components/StatusBadge";
import { Layers, RefreshCw, Eye, EyeOff } from "lucide-react";

// Leaflet loaded only client-side
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Fix default marker icon (webpack asset issue)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

interface LayerState {
  image: ImageRecord;
  wmsUrl: string | null;
  layerName: string | null;
  visible: boolean;
  leafletLayer: L.TileLayer.WMS | null;
}

export default function MapClient({ initialLayerName, initialImageId }: { initialLayerName?: string; initialImageId?: string }) {
  const mapRef = useRef<L.Map | null>(null);
  const mapElRef = useRef<HTMLDivElement>(null);
  const [layers, setLayers] = useState<LayerState[]>([]);
  const [loadingLayers, setLoadingLayers] = useState(false);

  // Init map once
  useEffect(() => {
    if (mapRef.current || !mapElRef.current) return;

    const map = L.map(mapElRef.current, {
      center: [-15.78, -47.93], // Brasília
      zoom: 4,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Load published images
  const loadPublishedImages = async () => {
    if (!mapRef.current) return;
    setLoadingLayers(true);
    try {
      const images = await getImages("published");
      const newLayers: LayerState[] = [];

      for (const img of images) {
        if (!img.layer_name) continue;
        try {
          newLayers.push({
            image: img,
            // Always use same-origin API proxy to avoid mixed-content/TLS issues.
            wmsUrl: `/api/services/${img.id}/wms-proxy`,
            layerName: img.layer_name,
            visible: img.id === initialImageId || img.layer_name === initialLayerName,
            leafletLayer: null,
          });
        } catch {
          newLayers.push({
            image: img,
            wmsUrl: null,
            layerName: img.layer_name,
            visible: false,
            leafletLayer: null,
          });
        }
      }

      setLayers(newLayers);
    } finally {
      setLoadingLayers(false);
    }
  };

  useEffect(() => {
    loadPublishedImages();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync Leaflet WMS layers when `layers` state changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    setLayers((prev) =>
      prev.map((ls) => {
        if (ls.visible && ls.wmsUrl && ls.layerName) {
          if (!ls.leafletLayer) {
            const wmsLayer = L.tileLayer.wms(ls.wmsUrl, {
              layers: ls.layerName,
              format: "image/png",
              transparent: true,
              version: "1.1.1",
              attribution: ls.image.filename,
            });
            wmsLayer.addTo(map);

            // Fly to bbox if available
            const bbox = ls.image.bbox;
            if (bbox) {
              map.flyToBounds([
                [bbox.miny, bbox.minx],
                [bbox.maxy, bbox.maxx],
              ], { maxZoom: 14, duration: 1.2 });
            }

            return { ...ls, leafletLayer: wmsLayer };
          }
        } else if (!ls.visible && ls.leafletLayer) {
          map.removeLayer(ls.leafletLayer);
          return { ...ls, leafletLayer: null };
        }
        return ls;
      })
    );
  }, [layers.map((l) => `${l.image.id}:${l.visible}`).join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleLayer = (imageId: string) => {
    setLayers((prev) =>
      prev.map((ls) =>
        ls.image.id === imageId ? { ...ls, visible: !ls.visible } : ls
      )
    );
  };

  const flyTo = (ls: LayerState) => {
    const map = mapRef.current;
    if (!map || !ls.image.bbox) return;
    const { minx, miny, maxx, maxy } = ls.image.bbox;
    map.flyToBounds([[miny, minx], [maxy, maxx]], { maxZoom: 14, duration: 1.2 });
  };

  return (
    <div className="relative flex h-full">
      {/* Map */}
      <div ref={mapElRef} className="flex-1 h-full z-0" />

      {/* Layer panel */}
      <div className="absolute top-4 right-4 z-[1000] w-64 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2 font-semibold text-sm text-gray-700">
            <Layers className="w-4 h-4" />
            Camadas publicadas
          </div>
          <button
            onClick={loadPublishedImages}
            className="p-1 rounded hover:bg-gray-100 text-gray-400"
            title="Recarregar"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loadingLayers && "animate-spin")} />
          </button>
        </div>

        {loadingLayers && layers.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-gray-400">Carregando…</div>
        ) : layers.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-gray-400">
            Nenhuma imagem publicada.<br />
            <span className="text-xs">Faça upload e aguarde o processamento.</span>
          </div>
        ) : (
          <ul className="divide-y divide-gray-50 max-h-80 overflow-y-auto">
            {layers.map((ls) => (
              <li key={ls.image.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <button
                      onClick={() => flyTo(ls)}
                      className="text-sm font-medium text-gray-700 truncate block text-left hover:text-brand-600 w-full"
                      title="Centralizar no mapa"
                    >
                      {ls.image.filename}
                    </button>
                    <div className="mt-1">
                      <StatusBadge status={ls.image.status} />
                    </div>
                    {ls.image.crs && (
                      <span className="text-xs text-gray-400 font-mono mt-1 block">{ls.image.crs}</span>
                    )}
                  </div>
                  <button
                    onClick={() => toggleLayer(ls.image.id)}
                    disabled={!ls.wmsUrl}
                    className={cn(
                      "p-1.5 rounded-lg shrink-0 transition-colors",
                      ls.visible
                        ? "bg-brand-100 text-brand-600 hover:bg-brand-200"
                        : "text-gray-300 hover:bg-gray-100 hover:text-gray-500",
                      !ls.wmsUrl && "opacity-30 cursor-not-allowed"
                    )}
                    title={ls.visible ? "Ocultar camada" : "Exibir camada"}
                  >
                    {ls.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
