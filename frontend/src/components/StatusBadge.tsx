import { cn, STATUS_COLOR, STATUS_LABEL } from "@/lib/utils";
import type { ImageStatus } from "@/lib/api";
import { Loader2 } from "lucide-react";

const SPINNING: ImageStatus[] = ["uploading", "processing", "publishing"];

export default function StatusBadge({ status }: { status: ImageStatus }) {
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium", STATUS_COLOR[status])}>
      {SPINNING.includes(status) && <Loader2 className="w-3 h-3 animate-spin" />}
      {STATUS_LABEL[status]}
    </span>
  );
}
