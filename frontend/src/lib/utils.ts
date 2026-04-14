import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ImageStatus } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const STATUS_LABEL: Record<ImageStatus, string> = {
  pending:    "Pendente",
  uploading:  "Enviando",
  uploaded:   "Enviado",
  processing: "Processando",
  processed:  "Processado",
  publishing: "Publicando",
  published:  "Publicado",
  error:      "Erro",
};

export const STATUS_COLOR: Record<ImageStatus, string> = {
  pending:    "bg-gray-100 text-gray-600",
  uploading:  "bg-blue-100 text-blue-700",
  uploaded:   "bg-sky-100 text-sky-700",
  processing: "bg-yellow-100 text-yellow-700",
  processed:  "bg-orange-100 text-orange-700",
  publishing: "bg-purple-100 text-purple-700",
  published:  "bg-green-100 text-green-700",
  error:      "bg-red-100 text-red-700",
};

export const STATUS_IS_ACTIVE: Record<ImageStatus, boolean> = {
  pending: false, uploading: true, uploaded: true,
  processing: true, processed: true, publishing: true,
  published: false, error: false,
};

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("pt-BR");
}
