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
  wfs_url: string | null;
  wmts_url: string | null;
  wcs_url: string | null;
  asset_kind?: string | null;
  source_format?: string | null;
  geometry_type?: string | null;
  workspace?: string | null;
  datastore?: string | null;
  postgis_table?: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface OGCServices {
  image_id: string;
  layer: string;
  services: {
    wms: { url: string; getcapabilities: string; getmap_example: string };
    wfs: { url: string; getcapabilities: string; getfeature_example: string };
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
  download_accesses: number;
  ogc_accesses: number;
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
  access_type: "all" | "download" | "ogc";
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

export interface UploadCostEstimateStatusItem {
  status: string;
  count: number;
}

export interface UploadCostEstimateAuditSession {
  session_id: string;
  status: string;
  filename: string;
  asset_type: string;
  size_gb: number;
  expected_monthly_downloads: number;
  first_month_total: number;
  recurring_monthly_total: number;
  currency: string;
  created_at: string | null;
  accepted_at: string | null;
  expires_at: string | null;
}

export interface UploadCostEstimateAuditResponse {
  tenant_id: string;
  window_days: number;
  totals: {
    sessions: number;
    estimated: number;
    accepted: number;
    consumed: number;
    expired_total: number;
  };
  rates: {
    acceptance_rate_pct: number;
    conversion_to_upload_pct: number;
  };
  accepted_averages: {
    currency: string;
    first_month_total: number;
    recurring_monthly_total: number;
  };
  status_breakdown: UploadCostEstimateStatusItem[];
  recent_sessions: UploadCostEstimateAuditSession[];
}

export interface UploadCostEstimateCleanupResponse {
  tenant_id: string;
  deleted_count: number;
  limit: number;
  executed_at: string;
  oldest_expires_at: string | null;
  newest_expires_at: string | null;
}

export interface ImageDownloadUrlResponse {
  image_id: string;
  source: "raw" | "processed";
  bucket: string;
  object_key: string;
  download_url: string;
  expires_in_seconds: number;
}

export interface UploadCostEstimateAssumptions {
  expected_monthly_downloads: number;
  avg_download_size_ratio: number;
  processed_size_ratio_raster: number;
  processed_size_ratio_vector: number;
  processing_base_units: number;
  processing_units_per_gb_raster: number;
  processing_units_per_gb_vector: number;
  uncertainty_min_factor: number;
  uncertainty_max_factor: number;
}

export interface UploadCostEstimateConfigResponse {
  tenant_id: string;
  is_enabled: boolean;
  assumptions: UploadCostEstimateAssumptions;
  source: string;
}

export interface UploadCostEstimateAnalysis {
  filename: string;
  extension: string;
  asset_type: "raster" | "vector";
  size_bytes: number;
  size_gb: number;
  complexity_factor: number;
  analysis_mode: string;
}

export interface UploadCostEstimate {
  currency: string;
  analysis_snapshot: {
    asset_type: "raster" | "vector";
    size_gb: number;
    complexity_factor: number;
  };
  assumptions_used: {
    expected_monthly_downloads: number;
    avg_download_size_ratio: number;
    processed_size_ratio: number;
  };
  breakdown: {
    processing_one_time: number;
    storage_monthly: number;
    publication_monthly: number;
    recurring_monthly_total: number;
    first_month_total: number;
    first_month_range: {
      minimum: number;
      likely: number;
      maximum: number;
    };
  };
  resource_projection: {
    raw_storage_gb: number;
    processed_storage_gb: number;
    total_storage_gb: number;
    processing_units: number;
  };
}

export interface UploadCostEstimateStartResponse {
  session_id: string;
  tenant_id: string;
  expires_at: string;
  feature_enabled: boolean;
  analysis: UploadCostEstimateAnalysis;
  estimate: UploadCostEstimate;
  temp_upload: {
    bucket: string;
    object_key: string;
    upload_url: string;
    expires_in: number;
  };
}

export interface UploadCostEstimateCalculateResponse {
  session_id: string;
  tenant_id: string;
  expires_at: string;
  analysis: UploadCostEstimateAnalysis;
  estimate: UploadCostEstimate;
}

export interface UploadCostEstimateAcceptResponse {
  session_id: string;
  tenant_id: string;
  status: string;
  accepted_at: string;
  expires_at: string;
  analysis: UploadCostEstimateAnalysis;
  estimate: UploadCostEstimate;
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

export async function getStorageMetrics(
  windowDays = 30,
  tenantId?: string,
  accessType: "all" | "download" | "ogc" = "all"
): Promise<StorageMetrics> {
  const query = new URLSearchParams({ window_days: String(windowDays) });
  if (tenantId) query.set("tenant_id", tenantId);
  query.set("access_type", accessType);
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

export async function getUploadCostEstimateAudit(
  windowDays = 30,
  tenantId?: string,
  limit = 20
): Promise<UploadCostEstimateAuditResponse> {
  const query = new URLSearchParams({
    window_days: String(windowDays),
    limit: String(limit),
  });
  if (tenantId) query.set("tenant_id", tenantId);
  return req<UploadCostEstimateAuditResponse>(`/api/metrics/upload-cost-estimates?${query.toString()}`);
}

export async function cleanupUploadCostEstimateSessions(input?: {
  tenant_id?: string;
  limit?: number;
}): Promise<UploadCostEstimateCleanupResponse> {
  return req<UploadCostEstimateCleanupResponse>("/api/metrics/upload-cost-estimates/cleanup", {
    method: "POST",
    body: JSON.stringify({
      tenant_id: input?.tenant_id,
      limit: input?.limit ?? 500,
    }),
  });
}

export async function requestSignedUrl(
  filename: string,
  contentType: string,
  sizeBytes?: number
): Promise<{ image_id: string; upload_url: string; raw_key: string; content_type: string }> {
  return req("/api/upload/signed-url", {
    method: "POST",
    body: JSON.stringify({ filename, content_type: contentType, size_bytes: sizeBytes }),
  });
}

export async function uploadFileDirect(
  uploadUrl: string,
  file: File,
  onProgress?: (pct: number) => void,
  signedContentType?: string
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    const contentType = signedContentType || file.type || "application/octet-stream";
    xhr.setRequestHeader("Content-Type", contentType);
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

export async function confirmUpload(imageId: string, estimateSessionId?: string): Promise<void> {
  await req("/api/upload/confirm", {
    method: "POST",
    body: JSON.stringify({
      image_id: imageId,
      estimate_session_id: estimateSessionId,
    }),
  });
}

export async function getUploadCostEstimateConfig(
  tenantId?: string
): Promise<UploadCostEstimateConfigResponse> {
  const query = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return req<UploadCostEstimateConfigResponse>(`/api/upload/cost-estimate/config${query}`);
}

export async function startUploadCostEstimate(input: {
  filename: string;
  sizeBytes: number;
  contentType: string;
  tenantId?: string;
}): Promise<UploadCostEstimateStartResponse> {
  return req<UploadCostEstimateStartResponse>("/api/upload/cost-estimate/start", {
    method: "POST",
    body: JSON.stringify({
      filename: input.filename,
      size_bytes: input.sizeBytes,
      content_type: input.contentType,
      tenant_id: input.tenantId,
    }),
  });
}

export async function recalculateUploadCostEstimate(input: {
  sessionId: string;
  expectedMonthlyDownloads?: number;
  avgDownloadSizeRatio?: number;
}): Promise<UploadCostEstimateCalculateResponse> {
  return req<UploadCostEstimateCalculateResponse>("/api/upload/cost-estimate/calculate", {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId,
      expected_monthly_downloads: input.expectedMonthlyDownloads,
      avg_download_size_ratio: input.avgDownloadSizeRatio,
    }),
  });
}

export async function acceptUploadCostEstimate(input: {
  sessionId: string;
  expectedMonthlyDownloads?: number;
  avgDownloadSizeRatio?: number;
}): Promise<UploadCostEstimateAcceptResponse> {
  return req<UploadCostEstimateAcceptResponse>("/api/upload/cost-estimate/accept", {
    method: "POST",
    body: JSON.stringify({
      session_id: input.sessionId,
      expected_monthly_downloads: input.expectedMonthlyDownloads,
      avg_download_size_ratio: input.avgDownloadSizeRatio,
    }),
  });
}

export async function deleteImage(id: string): Promise<void> {
  const r = await fetch(`${BASE}/api/images/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`${r.status}`);
}
