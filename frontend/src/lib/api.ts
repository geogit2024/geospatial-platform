const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
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

export async function requestSignedUrl(
  filename: string,
  contentType: string
): Promise<{ image_id: string; upload_url: string; raw_key: string }> {
  return req(`/api/upload/signed-url`, {
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
  await req(`/api/upload/confirm`, {
    method: "POST",
    body: JSON.stringify({ image_id: imageId }),
  });
}

export async function deleteImage(id: string): Promise<void> {
  const r = await fetch(`${BASE}/api/images/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`${r.status}`);
}
