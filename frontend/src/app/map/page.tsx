import dynamic from "next/dynamic";
import { Suspense } from "react";

// Leaflet only on client
const MapClient = dynamic(() => import("./MapClient"), { ssr: false });

function MapLoader() {
  return (
    <div className="flex-1 flex items-center justify-center bg-[#0b1220] text-[#9fb3cf] text-sm">
      Carregando mapa...
    </div>
  );
}

export default function MapPage({
  searchParams,
}: {
  searchParams?: { layer?: string; imageId?: string };
}) {
  return (
    <div className="h-full flex flex-col bg-[#0b1220]/70">
      <div className="px-6 py-4 border-b border-[#1f2d44] bg-[#0f1a2b] shrink-0">
        <h1 className="text-lg font-bold text-[#e2ecff]">Mapa WebGIS</h1>
        <p className="text-xs text-[#8fa8c6] mt-0.5">WMS - WMTS - WCS - camadas publicadas via GeoServer</p>
      </div>
      <div className="flex-1 relative overflow-hidden">
        <Suspense fallback={<MapLoader />}>
          <MapClient initialLayerName={searchParams?.layer} initialImageId={searchParams?.imageId} />
        </Suspense>
      </div>
    </div>
  );
}
