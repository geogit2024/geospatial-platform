"use client";
import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileImage, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { requestSignedUrl, uploadFileDirect, confirmUpload } from "@/lib/api";
import { cn } from "@/lib/utils";
import { registerImageOwner } from "@/lib/auth";

type Step = "idle" | "signing" | "uploading" | "confirming" | "done" | "error";

const ACCEPTED = [".tif", ".tiff", ".geotiff", ".jp2", ".ecw", ".img"];
const ACCEPT_MIME = "image/tiff,.tif,.tiff,.geotiff,.jp2,.ecw,.img";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadingRef = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [progress, setProgress] = useState(0);
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (f: File) => {
    const ext = "." + f.name.split(".").pop()!.toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`Formato nao suportado: ${ext}. Use: ${ACCEPTED.join(", ")}`);
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
      registerImageOwner(image_id);

      setStep("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
      setStep("error");
    } finally {
      uploadingRef.current = false;
    }
  };

  const STEP_LABEL: Record<Step, string> = {
    idle: "",
    signing: "Gerando URL segura...",
    uploading: `Enviando ${progress}%`,
    confirming: "Enfileirando processamento...",
    done: "Upload concluido! Processamento iniciado.",
    error: "",
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 text-[#dbe8fb]">
      <h1 className="text-2xl font-bold mb-1 text-[#e2ecff]">Upload de Imagem</h1>
      <p className="text-[#9fb3cf] mb-8">
        Formatos suportados: GeoTIFF, JP2, ECW, IMG. Upload direto para o storage - a API nao transita os bytes.
      </p>

      <div
        className={cn(
          "border-2 border-dashed rounded-xl p-10 flex flex-col items-center gap-4 cursor-pointer transition-colors",
          dragging ? "border-[#38bdf8] bg-[#13263d]" : "border-[#2a3f58] hover:border-[#38bdf8] bg-[#101b2c]"
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
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
            <FileImage className="w-12 h-12 text-[#38bdf8]" />
            <div className="text-center">
              <p className="font-semibold text-[#dbe8fb]">{file.name}</p>
              <p className="text-sm text-[#9fb3cf]">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </>
        ) : (
          <>
            <Upload className="w-12 h-12 text-[#7f97b5]" />
            <div className="text-center">
              <p className="font-semibold text-[#dbe8fb]">Arraste e solte ou clique para selecionar</p>
              <p className="text-sm text-[#9fb3cf] mt-1">{ACCEPTED.join("  ")}</p>
            </div>
          </>
        )}
      </div>

      {step === "uploading" && (
        <div className="mt-4 w-full bg-[#1d2b3e] rounded-full h-2">
          <div className="bg-[#38bdf8] h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>
      )}

      {step !== "idle" && step !== "error" && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          {step === "done" ? (
            <CheckCircle2 className="w-4 h-4 text-green-400" />
          ) : (
            <Loader2 className="w-4 h-4 text-[#38bdf8] animate-spin" />
          )}
          <span className={step === "done" ? "text-green-400 font-medium" : "text-[#9fb3cf]"}>{STEP_LABEL[step]}</span>
        </div>
      )}

      {error && (
        <div className="mt-4 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <div className="mt-6 flex gap-3">
        {step !== "done" ? (
          <button
            onClick={startUpload}
            disabled={!file || !["idle", "error"].includes(step)}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm transition-colors",
              file && ["idle", "error"].includes(step)
                ? "bg-[#1d4f7a] text-[#dff4ff] hover:bg-[#25608f]"
                : "bg-[#1d2b3e] text-[#7f97b5] cursor-not-allowed"
            )}
          >
            <Upload className="w-4 h-4" />
            Iniciar Upload e Processamento
          </button>
        ) : (
          <>
            <button
              onClick={() => router.push("/dashboard")}
              className="px-5 py-2.5 rounded-lg bg-[#1d4f7a] text-[#dff4ff] font-medium text-sm hover:bg-[#25608f]"
            >
              Ver no Dashboard
            </button>
            <button
              onClick={() => {
                setFile(null);
                setStep("idle");
                setProgress(0);
                setImageId(null);
              }}
              className="px-5 py-2.5 rounded-lg border border-[#2a3f58] text-[#9fb3cf] font-medium text-sm hover:bg-[#122033]"
            >
              Novo Upload
            </button>
          </>
        )}
      </div>

      {imageId && step === "done" && (
        <p className="mt-3 text-xs text-[#8aa2c4]">
          ID da imagem: <code className="bg-[#0c1727] px-1 py-0.5 rounded">{imageId}</code>
        </p>
      )}
    </div>
  );
}

