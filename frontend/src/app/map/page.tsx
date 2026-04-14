import dynamic from "next/dynamic";
import { Suspense } from "react";

// Leaflet cannot run on the server — load the whole map client-side
const MapClient = dynamic(() => import("./MapClient"), { ssr: false });

function MapLoader() {
  return (
    <div className="flex-1 flex items-center justify-center bg-gray-100 text-gray-400 text-sm">
      Carregando mapa…
    </div>
  );
}

export default function MapPage({
  searchParams,
}: {
  searchParams?: { layer?: string; imageId?: string };
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="px-6 py-4 border-b border-gray-200 bg-white shrink-0">
        <h1 className="text-lg font-bold">Mapa WebGIS</h1>
        <p className="text-xs text-gray-400 mt-0.5">WMS · WMTS · WCS — camadas publicadas via GeoServer</p>
      </div>
      <div className="flex-1 relative overflow-hidden">
        <Suspense fallback={<MapLoader />}>
          <MapClient
            initialLayerName={searchParams?.layer}
            initialImageId={searchParams?.imageId}
          />
        </Suspense>
      </div>
    </div>
  );
}
