"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { VisualReviewCard } from "@/components/visual-review-card";
import { AppShell } from "@/components/shell/app-shell";
import { api, ApiError } from "@/lib/api";

interface AssetItem {
  id: string;
  original_name: string;
  mime_type: string;
  file_size_bytes: number;
  asset_type: string;
  status: string;
  width: number | null;
  height: number | null;
  created_at: string | null;
}

interface AnalysisResult {
  id: string;
  summary: string;
  strengths: string[];
  improvements: {
    priority: "high" | "medium" | "low";
    area: string;
    reason: string;
    action: string;
  }[];
  revised_copy: string | null;
  accessibility_notes: string[];
  review_mode: "technical" | "visual";
}

export default function LibraryPage() {
  const router = useRouter();
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(
    null
  );
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadAssets();
  }, []);

  async function loadAssets() {
    setLoading(true);
    setError("");
    try {
      const data = await api.assets.list();
      setAssets(data as unknown as AssetItem[]);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error al cargar la biblioteca.");
      }
    } finally {
      setLoading(false);
    }
  }

  const handleUpload = useCallback(async () => {
    const files = fileRef.current?.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    setError("");
    try {
      const result = await api.assets.upload(files[0]);
      if (result.status === "error") {
        setError(result.message as string);
      } else {
        await loadAssets();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error al subir el archivo.");
      }
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, []);

  const handleAnalyze = useCallback(async (assetId: string) => {
    setAnalyzing(assetId);
    setError("");
    setAnalysisResult(null);
    try {
      const result = await api.assets.analyze(assetId);
      setAnalysisResult(result as unknown as AnalysisResult);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error al analizar la imagen.");
      }
    } finally {
      setAnalyzing(null);
    }
  }, []);

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <AppShell>
    <main className="app-page app-page--narrow"
      style={{
        maxWidth: 800,
        margin: "0 auto",
        padding: "32px 24px",
        minHeight: "100vh",
      }}
    >
      <header style={{ marginBottom: 32 }}>
        <button
          onClick={() => router.push("/")}
          style={{
            background: "none",
            border: "none",
            color: "var(--primary)",
            cursor: "pointer",
            padding: 0,
            marginBottom: 8,
            display: "block",
          }}
        >
          &larr; Volver
        </button>
        <h1
          style={{
            fontFamily: "var(--font-heading)",
            fontSize: "1.8rem",
            margin: 0,
            color: "var(--foreground)",
          }}
        >
          Biblioteca
        </h1>
        <p style={{ color: "var(--muted-foreground)", margin: "4px 0 0" }}>
          Tus imágenes y activos subidos.
        </p>
      </header>

      <div
        style={{
          padding: 24,
          border: "2px dashed var(--border)",
          borderRadius: "var(--radius-lg)",
          textAlign: "center",
          marginBottom: 32,
          background: "var(--surface)",
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={handleUpload}
          disabled={uploading}
          style={{ display: "none" }}
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          style={{
            display: "inline-block",
            padding: "14px 28px",
            background: uploading ? "var(--border)" : "var(--gradient-primary)",
            color: "var(--primary-foreground)",
            borderRadius: "var(--radius-md)",
            cursor: uploading ? "not-allowed" : "pointer",
            fontWeight: 600,
          }}
        >
          {uploading ? "Subiendo..." : "Subir imagen"}
        </label>
        <p
          style={{
            color: "var(--muted-foreground)",
            fontSize: "0.85rem",
            marginTop: 8,
          }}
        >
          JPEG, PNG o WebP. Máximo 10 MB.
        </p>
        <p
          style={{
            color: "var(--muted-foreground)",
            fontSize: "0.8rem",
            margin: 0,
          }}
        >
          Una revisión visual puede enviar esta imagen al proveedor de IA que
          configure tu organización. El modo local no la envía fuera de
          HiTrendy.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            padding: "12px 16px",
            background: "#fef2f2",
            color: "#b91c1c",
            borderRadius: "var(--radius-md)",
            marginBottom: 16,
            border: "1px solid #fecaca",
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: "var(--muted-foreground)" }}>Cargando...</p>
      ) : assets.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: 48,
            color: "var(--muted-foreground)",
          }}
        >
          <p>Aún no has subido ningún activo.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {assets.map((asset) => (
            <div
              key={asset.id}
              style={{
                padding: "16px 20px",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                display: "flex",
                gap: 16,
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <a
                href={api.assets.contentUrl(asset.id)}
                target="_blank"
                rel="noopener noreferrer"
                title={`Abrir ${asset.original_name} en pestaña nueva`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  minWidth: 0,
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <Image
                  src={api.assets.contentUrl(asset.id)}
                  alt={`Vista previa de ${asset.original_name}`}
                  width={56}
                  height={56}
                  unoptimized
                  style={{
                    width: 56,
                    height: 56,
                    objectFit: "cover",
                    flexShrink: 0,
                    borderRadius: "var(--radius-sm)",
                    background: "var(--muted)",
                    cursor: "pointer",
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <strong
                    style={{
                      color: "var(--foreground)",
                      display: "block",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={asset.original_name}
                  >
                    {asset.original_name}
                  </strong>
                  <span
                    style={{
                      fontSize: "0.8rem",
                      color: "var(--muted-foreground)",
                    }}
                  >
                    {formatSize(asset.file_size_bytes)}
                    {asset.width && asset.height
                      ? ` · ${asset.width} × ${asset.height} px`
                      : ""}
                  </span>
                </div>
              </a>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <a
                  href={api.assets.contentUrl(asset.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    padding: "6px 14px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--surface)",
                    fontWeight: 600,
                    fontSize: "0.85rem",
                    textDecoration: "none",
                    color: "var(--foreground)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  Abrir ↗
                </a>
                <button
                  type="button"
                  onClick={() => handleAnalyze(asset.id)}
                  disabled={analyzing === asset.id}
                  style={{
                    padding: "6px 14px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--surface)",
                    color: "var(--foreground)",
                    cursor: analyzing === asset.id ? "not-allowed" : "pointer",
                    fontWeight: 600,
                    fontSize: "0.85rem",
                    opacity: analyzing === asset.id ? 0.6 : 1,
                  }}
                >
                  {analyzing === asset.id ? "Analizando..." : "Analizar"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {analysisResult && (
        <div style={{ marginTop: 32 }}>
          <p style={{ color: "var(--muted-foreground)", fontSize: "0.85rem" }}>
            {analysisResult.review_mode === "technical"
              ? "Esta revisión local confirma metadatos técnicos. Para recomendaciones sobre composición, contraste o texto se requiere un proveedor de visión configurado."
              : "Esta revisión se generó con el proveedor de visión configurado y se validó antes de mostrarse."}
          </p>
          <VisualReviewCard analysis={analysisResult} />
        </div>
      )}
    </main>
    </AppShell>
  );
}
