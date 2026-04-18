// Use relative /api so frontend always calls the local Next.js proxy route.
// Proxy target is resolved at runtime via API_URL (Cloud Run-friendly).
const BASE = "";

export type ImageStatus =
  | "pending" | "uploading" | "uploaded" | "processing"
  | "processed" | "publishing" | "published" | "error";

export interface ImageRecord {
  id: string;
  filename: string;
  status: ImageStatus;
  crs: string | null;
  bbox: { minx: number; miny: number; maxx: number; maxy: number } | null;
  layer_name: string | null;
  wms_url: string | null;
  wmts_url: string | null;
  wcs_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface OGCServices {
  image_id: string;
  layer: string;
  services: {
    wms: { url: string; getcapabilities: string; getmap_example: string };
    wmts: { url: string; getcapabilities: string };
    wcs: { url: string; getcapabilities: string };
  };
  bbox: { minx: number; miny: number; maxx: number; maxy: number } | null;
}

export interface DistributionByType {
  type: string;
  count: number;
  size_gb: number;
}

export interface TopFileMetric {
  id: string;
  filename: string;
  size_mb: number;
  created_at: string;
}

export interface TopAccessedMetric {
  id: string;
  filename: string;
  accesses: number;
}

export interface UsageSeriesPoint {
  date: string;
  files_added: number;
  added_gb: number;
  total_gb: number;
}

export interface StorageMetrics {
  tenant_id: string;
  window_days: number;
  total_files: number;
  total_size_gb: number;
  avg_size_mb: number;
  growth_window_pct: number;
  growth_30_days: number | null;
  distribution_by_type: DistributionByType[];
  top_files: TopFileMetric[];
  top_accessed: TopAccessedMetric[];
  usage_timeseries: UsageSeriesPoint[];
}

export interface CostSeriesPoint {
  date: string;
  value: number;
  storage: number;
  processing: number;
  downloads: number;
}

export interface CostMetrics {
  tenant_id: string;
  window_days: number;
  cost_source: string;
  cost_source_is_real: boolean;
  cost_source_table?: string | null;
  currency: string;
  cost_per_gb: number;
  cost_per_process: number;
  cost_per_download: number;
  storage_cost_month: number;
  processing_cost: number;
  download_cost: number;
  estimated_total: number;
  projection_30_days: number;
  cost_timeseries: CostSeriesPoint[];
}

export interface CostSimulationResponse {
  tenant_id: string;
  currency: string;
  current_estimated_total: number;
  extra_storage_cost: number;
  extra_processing_cost: number;
  extra_download_cost: number;
  extra_total: number;
  new_estimated_total: number;
}

export interface ImageDownloadUrlResponse {
  image_id: string;
  source: "raw" | "processed";
  bucket: string;
  object_key: string;
  download_url: string;
  expires_in_seconds: number;
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    let detail = "";
    try {
      const payload = await r.json();
      detail = typeof payload?.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `${r.status} ${detail}` : `${r.status} ${r.statusText}`);
  }
  return r.json();
}

export async function getImages(status?: string): Promise<ImageRecord[]> {
  const qs = status ? `?status=${status}` : "";
  return req<ImageRecord[]>(`/api/images/${qs}`);
}

export async function getImage(id: string): Promise<ImageRecord> {
  return req<ImageRecord>(`/api/images/${id}`);
}

export async function getOGCServices(id: string): Promise<OGCServices> {
  return req<OGCServices>(`/api/services/${id}/ogc`);
}

export async function getImageDownloadUrl(
  id: string,
  source: "raw" | "processed" = "raw"
): Promise<ImageDownloadUrlResponse> {
  return req<ImageDownloadUrlResponse>(`/api/images/${id}/download-url?source=${source}`);
}

export async function getStorageMetrics(windowDays = 30, tenantId?: string): Promise<StorageMetrics> {
  const query = new URLSearchParams({ window_days: String(windowDays) });
  if (tenantId) query.set("tenant_id", tenantId);
  return req<StorageMetrics>(`/api/metrics/storage?${query.toString()}`);
}

export async function getCostMetrics(windowDays = 30, tenantId?: string): Promise<CostMetrics> {
  const query = new URLSearchParams({ window_days: String(windowDays) });
  if (tenantId) query.set("tenant_id", tenantId);
  return req<CostMetrics>(`/api/metrics/costs?${query.toString()}`);
}

export async function simulateCostMetrics(input: {
  tenant_id?: string;
  window_days?: number;
  extra_gb: number;
  extra_processes: number;
  extra_downloads: number;
}): Promise<CostSimulationResponse> {
  return req<CostSimulationResponse>("/api/metrics/costs/simulate", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function requestSignedUrl(
  filename: string,
  contentType: string
): Promise<{ image_id: string; upload_url: string; raw_key: string }> {
  return req("/api/upload/signed-url", {
    method: "POST",
    body: JSON.stringify({ filename, content_type: contentType }),
  });
}

export async function uploadFileDirect(
  uploadUrl: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", file.type || "image/tiff");
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`Upload failed: ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.send(file);
  });
}

export async function confirmUpload(imageId: string): Promise<void> {
  await req("/api/upload/confirm", {
    method: "POST",
    body: JSON.stringify({ image_id: imageId }),
  });
}

export async function deleteImage(id: string): Promise<void> {
  const r = await fetch(`${BASE}/api/images/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`${r.status}`);
}
