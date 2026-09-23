"use client";

import { useId, useState } from "react";

import { printPlan } from "@/lib/plan-export";

export interface AdvisorRecommendation {
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
}

export interface AdvisorData {
  summary: string;
  recommendations: AdvisorRecommendation[];
  next_actions: string[];
}

interface Props {
  advisor: AdvisorData;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "var(--danger, #ef4444)",
  medium: "var(--warning, #f59e0b)",
  low: "var(--primary, #6366f1)",
};

const PRIORITY_LABELS: Record<string, string> = {
  high: "Alta prioridad",
  medium: "Media prioridad",
  low: "Sugerencia",
};

export function AdvisorResponseCard({ advisor }: Props) {
  const titleId = useId();
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopyAction = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <article
      className="artifact-card"
      style={{
        marginTop: 12,
        background: "var(--surface, #1e1e24)",
        border: "1px solid var(--border, rgba(255,255,255,0.1))",
        borderRadius: "var(--radius-md, 12px)",
        padding: "20px",
      }}
      aria-labelledby={titleId}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
          marginBottom: "12px",
        }}
      >
        <span
          style={{
            background: "rgba(99, 102, 241, 0.15)",
            color: "var(--primary, #818cf8)",
            padding: "4px 10px",
            borderRadius: "999px",
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
          }}
        >
          💡 Plan de Contenido & Asesoría
        </span>
        {/* The plan is something a business takes off the screen: printing it
            from an isolated frame is what turns it into a PDF file, with no
            extra dependency and nothing the browser will block. */}
        <button
          type="button"
          className="advisor-export"
          onClick={() => printPlan(advisor)}
        >
          Descargar PDF
        </button>
      </div>

      <section style={{ marginBottom: "18px" }}>
        <h3 id={titleId} style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 8px 0" }}>
          Estrategia Recomendada
        </h3>
        <p style={{ margin: 0, fontSize: "0.92rem", lineHeight: 1.5, color: "var(--foreground, #f3f4f6)" }}>
          {advisor.summary}
        </p>
      </section>

      {advisor.recommendations && advisor.recommendations.length > 0 && (
        <section style={{ marginBottom: "18px" }}>
          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, margin: "0 0 12px 0", color: "var(--muted-foreground, #9ca3af)" }}>
            Ideas y Publicaciones de la Semana
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {advisor.recommendations.map((rec, i) => (
              <div
                key={i}
                style={{
                  padding: "12px 14px",
                  borderRadius: "8px",
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.06)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "8px",
                    marginBottom: "6px",
                  }}
                >
                  <strong style={{ fontSize: "0.9rem", color: "#ffffff" }}>{rec.title}</strong>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "999px",
                      background: `color-mix(in srgb, ${PRIORITY_COLORS[rec.priority] || PRIORITY_COLORS.medium} 20%, transparent)`,
                      color: PRIORITY_COLORS[rec.priority] || PRIORITY_COLORS.medium,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {PRIORITY_LABELS[rec.priority] || PRIORITY_LABELS.medium}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: "0.85rem", lineHeight: 1.4, color: "var(--muted-foreground, #d1d5db)" }}>
                  {rec.description}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {advisor.next_actions && advisor.next_actions.length > 0 && (
        <section>
          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, margin: "0 0 10px 0", color: "var(--muted-foreground, #9ca3af)" }}>
            Próximos Pasos de Acción
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {advisor.next_actions.map((act, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  background: "rgba(99, 102, 241, 0.06)",
                  border: "1px solid rgba(99, 102, 241, 0.15)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ color: "var(--primary, #818cf8)", fontWeight: 700, fontSize: "0.85rem" }}>
                    {i + 1}.
                  </span>
                  <span style={{ fontSize: "0.85rem", color: "#f3f4f6" }}>{act}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleCopyAction(act, i)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "0.75rem",
                    color: copiedIndex === i ? "#10b981" : "var(--primary, #818cf8)",
                    fontWeight: 600,
                    padding: "4px 8px",
                  }}
                >
                  {copiedIndex === i ? "✓ Copiado" : "Copiar"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
