"use client";
import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileImage, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { requestSignedUrl, uploadFileDirect, confirmUpload } from "@/lib/api";
import { cn } from "@/lib/utils";

type Step = "idle" | "signing" | "uploading" | "confirming" | "done" | "error";

const ACCEPTED = [".tif", ".tiff", ".geotiff", ".jp2", ".ecw", ".img"];
const ACCEPT_MIME = "image/tiff,.tif,.tiff,.geotiff,.jp2,.ecw,.img";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadingRef = useRef(false);           // sync guard against double-submit
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [progress, setProgress] = useState(0);
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (f: File) => {
    const ext = "." + f.name.split(".").pop()!.toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`Formato não suportado: ${ext}. Use: ${ACCEPTED.join(", ")}`);
      return;
    }
    setFile(f);
    setError(null);
    setStep("idle");
    setProgress(0);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const startUpload = async () => {
    if (!file || uploadingRef.current) return;
    uploadingRef.current = true;
    setError(null);
    try {
      setStep("signing");
      const { image_id, upload_url } = await requestSignedUrl(file.name, file.type || "image/tiff");
      setImageId(image_id);

      setStep("uploading");
      await uploadFileDirect(upload_url, file, setProgress);

      setStep("confirming");
      await confirmUpload(image_id);

      setStep("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
      setStep("error");
    } finally {
      uploadingRef.current = false;
    }
  };

  const STEP_LABEL: Record<Step, string> = {
    idle:       "",
    signing:    "Gerando URL segura...",
    uploading:  `Enviando ${progress}%`,
    confirming: "Enfileirando processamento...",
    done:       "Upload concluído! Processamento iniciado.",
    error:      "",
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1">Upload de Imagem</h1>
      <p className="text-gray-500 mb-8">
        Formatos suportados: GeoTIFF, JP2, ECW, IMG. Upload direto para o storage — a API não transita os bytes.
      </p>

      {/* Drop zone */}
      <div
        className={cn(
          "border-2 border-dashed rounded-xl p-10 flex flex-col items-center gap-4 cursor-pointer transition-colors",
          dragging ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 bg-white"
        )}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_MIME}
          className="hidden"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {file ? (
          <>
            <FileImage className="w-12 h-12 text-brand-500" />
            <div className="text-center">
              <p className="font-semibold text-gray-800">{file.name}</p>
              <p className="text-sm text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </>
        ) : (
          <>
            <Upload className="w-12 h-12 text-gray-400" />
            <div className="text-center">
              <p className="font-semibold text-gray-700">Arraste e solte ou clique para selecionar</p>
              <p className="text-sm text-gray-400 mt-1">{ACCEPTED.join("  ")}</p>
            </div>
          </>
        )}
      </div>

      {/* Progress bar */}
      {step === "uploading" && (
        <div className="mt-4 w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-brand-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Status */}
      {step !== "idle" && step !== "error" && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          {step === "done"
            ? <CheckCircle2 className="w-4 h-4 text-green-500" />
            : <Loader2 className="w-4 h-4 text-brand-500 animate-spin" />
          }
          <span className={step === "done" ? "text-green-700 font-medium" : "text-gray-600"}>
            {STEP_LABEL[step]}
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-4 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="mt-6 flex gap-3">
        {step !== "done" ? (
          <button
            onClick={startUpload}
            disabled={!file || !["idle", "error"].includes(step)}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm transition-colors",
              file && ["idle", "error"].includes(step)
                ? "bg-brand-500 text-white hover:bg-brand-600"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            )}
          >
            <Upload className="w-4 h-4" />
            Iniciar Upload e Processamento
          </button>
        ) : (
          <>
            <button
              onClick={() => router.push("/dashboard")}
              className="px-5 py-2.5 rounded-lg bg-brand-500 text-white font-medium text-sm hover:bg-brand-600"
            >
              Ver no Dashboard
            </button>
            <button
              onClick={() => { setFile(null); setStep("idle"); setProgress(0); setImageId(null); }}
              className="px-5 py-2.5 rounded-lg border border-gray-300 text-gray-600 font-medium text-sm hover:bg-gray-50"
            >
              Novo Upload
            </button>
          </>
        )}
      </div>

      {imageId && step === "done" && (
        <p className="mt-3 text-xs text-gray-400">ID da imagem: <code className="bg-gray-100 px-1 py-0.5 rounded">{imageId}</code></p>
      )}
    </div>
  );
}
