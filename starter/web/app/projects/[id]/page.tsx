"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { AppShell } from "@/components/shell/app-shell";
import type {
  GeneratedArtifact,
  GeneratedShortVideoScript,
} from "@/types/artifact";

interface ProjectData {
  id: string;
  name: string;
  platform: string;
  status: string;
  artifact_snapshot?: GeneratedArtifact | null;
  created_at: string | null;
}

interface VideoForm {
  hook: string;
  duration_seconds: string;
  scenes: Array<{
    order: number;
    duration_seconds: string;
    visual: string;
    on_screen_text: string;
    voiceover: string;
  }>;
  call_to_action: string;
  caption: string;
  assumptions: string[];
}

function videoFormFromArtifact(artifact: GeneratedShortVideoScript): VideoForm {
  return {
    hook: artifact.hook,
    duration_seconds: String(artifact.duration_seconds),
    scenes: artifact.scenes.map((scene) => ({
      ...scene,
      duration_seconds: String(scene.duration_seconds),
    })),
    call_to_action: artifact.call_to_action,
    caption: artifact.caption,
    assumptions: artifact.assumptions,
  };
}

export default function ProjectEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<ProjectData | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restoringVersionId, setRestoringVersionId] = useState<string | null>(
    null
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [versions, setVersions] = useState<
    Array<{
      id: string;
      version_number: number;
      user_edited: boolean;
      created_at: string | null;
    }>
  >([]);
  const [form, setForm] = useState({
    hook: "",
    caption: "",
    call_to_action: "",
    hashtags: "",
    visual_direction: "",
    format_recommendation: "static_post",
  });
  const [videoForm, setVideoForm] = useState<VideoForm>({
    hook: "",
    duration_seconds: "",
    scenes: [],
    call_to_action: "",
    caption: "",
    assumptions: [],
  });

  const loadProject = useCallback(async () => {
    setError("");
    try {
      const data = (await api.projects.get(
        params.id
      )) as unknown as ProjectData;
      setProject(data);
      setVersions(
        (await api.projects.versions(params.id)) as Array<{
          id: string;
          version_number: number;
          user_edited: boolean;
          created_at: string | null;
        }>
      );
      const snap = data.artifact_snapshot;
      if (snap?.artifact_type === "short_video_script") {
        setVideoForm(videoFormFromArtifact(snap));
      } else if (snap?.artifact_type === "social_post") {
        setForm({
          hook: snap.hook,
          caption: snap.caption,
          call_to_action: snap.call_to_action,
          hashtags: snap.hashtags.join(", "),
          visual_direction: snap.visual_direction,
          format_recommendation: snap.format_recommendation,
        });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error al cargar el proyecto.");
      }
    }
  }, [params.id]);

  useEffect(() => {
    if (!params.id) return;
    void loadProject();
  }, [loadProject, params.id]);

  const handleChange = useCallback((field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleVideoSceneChange = useCallback(
    (
      index: number,
      field: "duration_seconds" | "visual" | "on_screen_text" | "voiceover",
      value: string
    ) => {
      setVideoForm((current) => ({
        ...current,
        scenes: current.scenes.map((scene, sceneIndex) =>
          sceneIndex === index ? { ...scene, [field]: value } : scene
        ),
      }));
    },
    []
  );

  async function handleSave() {
    if (!project) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      if (project.artifact_snapshot?.artifact_type === "short_video_script") {
        await api.projects.updateArtifactVersion(project.id, {
          artifact_type: "short_video_script",
          hook: videoForm.hook,
          duration_seconds: Number(videoForm.duration_seconds),
          scenes: videoForm.scenes.map((scene) => ({
            ...scene,
            duration_seconds: Number(scene.duration_seconds),
          })),
          call_to_action: videoForm.call_to_action,
          caption: videoForm.caption,
          assumptions: videoForm.assumptions,
        });
      } else {
        const hashtags = form.hashtags
          .split(",")
          .map((h) => h.trim())
          .filter(Boolean);
        await api.projects.updateArtifactVersion(project.id, {
          artifact_type: "social_post",
          hook: form.hook,
          caption: form.caption,
          call_to_action: form.call_to_action,
          hashtags,
          visual_direction: form.visual_direction,
          format_recommendation: form.format_recommendation,
        });
      }
      setSuccess("Cambios guardados ✓");
      setEditing(false);
      await loadProject();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error al guardar los cambios.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    if (!project) return;
    setError("");
    try {
      const payload = await api.projects.export(project.id);
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${project.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "proyecto"}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setSuccess("Exportación preparada ✓");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No pudimos exportar el proyecto."
      );
    }
  }

  async function handleRestore(versionId: string, versionNumber: number) {
    if (!project) return;
    setRestoringVersionId(versionId);
    setError("");
    setSuccess("");
    try {
      const restored = await api.projects.restoreVersion(project.id, versionId);
      setSuccess(
        `Restauramos la versión ${versionNumber} como una nueva versión ${restored.version_number}.`
      );
      await loadProject();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No pudimos restaurar esta versión."
      );
    } finally {
      setRestoringVersionId(null);
    }
  }

  if (!project) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          color: "var(--muted-foreground)",
        }}
      >
        {error || "Cargando proyecto..."}
      </div>
    );
  }

  return (
    <AppShell>
    <main className="app-page app-page--narrow"
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: "32px 24px",
        minHeight: "100vh",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 32,
        }}
      >
        <div>
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
              fontSize: "1.6rem",
              margin: 0,
              color: "var(--foreground)",
            }}
          >
            {project.name}
          </h1>
          <p style={{ color: "var(--muted-foreground)", margin: "4px 0 0" }}>
            {project.platform}
          </p>
        </div>
        <span
          style={{
            fontSize: "0.8rem",
            padding: "4px 12px",
            borderRadius: "var(--radius-pill)",
            background:
              project.status === "active"
                ? "var(--surface-elevated)"
                : "var(--muted)",
            color: "var(--muted-foreground)",
          }}
        >
          {project.status === "active" ? "Activo" : "Archivado"}
        </span>
        <button
          type="button"
          onClick={handleExport}
          style={{
            padding: "8px 12px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface)",
            color: "var(--foreground)",
            cursor: "pointer",
          }}
        >
          Exportar JSON
        </button>
      </header>

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

      {success && (
        <div
          style={{
            padding: "12px 16px",
            background: "#f0fdf4",
            color: "#15803d",
            borderRadius: "var(--radius-md)",
            marginBottom: 16,
            border: "1px solid #bbf7d0",
          }}
        >
          {success}
        </div>
      )}

      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: 24,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {project.artifact_snapshot?.artifact_type === "short_video_script" ? (
            <>
              <Field
                label="Gancho"
                value={videoForm.hook}
                onChange={(v) => setVideoForm((current) => ({ ...current, hook: v }))}
                editing={editing}
              />
              <Field
                label="Duración total (segundos)"
                value={videoForm.duration_seconds}
                onChange={(v) =>
                  setVideoForm((current) => ({ ...current, duration_seconds: v }))
                }
                editing={editing}
              />
              <section aria-labelledby="video-scenes-title">
                <h2 id="video-scenes-title" style={{ fontSize: "1rem", margin: "0 0 12px" }}>
                  Escenas
                </h2>
                {videoForm.scenes.map((scene, index) => (
                  <div
                    key={scene.order}
                    style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 16 }}
                  >
                    <strong>Escena {scene.order}</strong>
                    <Field
                      label="Duración (segundos)"
                      value={scene.duration_seconds}
                      onChange={(v) => handleVideoSceneChange(index, "duration_seconds", v)}
                      editing={editing}
                    />
                    <Field
                      label="Visual"
                      value={scene.visual}
                      onChange={(v) => handleVideoSceneChange(index, "visual", v)}
                      editing={editing}
                      multiline
                    />
                    <Field
                      label="Texto en pantalla"
                      value={scene.on_screen_text}
                      onChange={(v) => handleVideoSceneChange(index, "on_screen_text", v)}
                      editing={editing}
                    />
                    <Field
                      label="Locución"
                      value={scene.voiceover}
                      onChange={(v) => handleVideoSceneChange(index, "voiceover", v)}
                      editing={editing}
                      multiline
                    />
                  </div>
                ))}
              </section>
              <Field
                label="Llamado a la acción"
                value={videoForm.call_to_action}
                onChange={(v) =>
                  setVideoForm((current) => ({ ...current, call_to_action: v }))
                }
                editing={editing}
              />
              <Field
                label="Caption sugerido"
                value={videoForm.caption}
                onChange={(v) => setVideoForm((current) => ({ ...current, caption: v }))}
                editing={editing}
                multiline
              />
            </>
          ) : (
            <>
              <Field
                label="Gancho"
                value={form.hook}
                onChange={(v) => handleChange("hook", v)}
                editing={editing}
              />
              <Field
                label="Texto principal"
                value={form.caption}
                onChange={(v) => handleChange("caption", v)}
                editing={editing}
                multiline
              />
              <Field
                label="Llamado a la acción"
                value={form.call_to_action}
                onChange={(v) => handleChange("call_to_action", v)}
                editing={editing}
              />
              <Field
                label="Hashtags"
                value={form.hashtags}
                onChange={(v) => handleChange("hashtags", v)}
                editing={editing}
              />
              <Field
                label="Dirección visual"
                value={form.visual_direction}
                onChange={(v) => handleChange("visual_direction", v)}
                editing={editing}
                multiline
              />
              <Field
                label="Formato"
                value={form.format_recommendation}
                onChange={(v) => handleChange("format_recommendation", v)}
                editing={editing}
              />
            </>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: 12,
            marginTop: 24,
            justifyContent: "flex-end",
          }}
        >
          {editing ? (
            <>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  const snap = project.artifact_snapshot;
                  if (snap?.artifact_type === "short_video_script") {
                    setVideoForm(videoFormFromArtifact(snap));
                  } else if (snap?.artifact_type === "social_post") {
                    setForm({
                      hook: snap.hook,
                      caption: snap.caption,
                      call_to_action: snap.call_to_action,
                      hashtags: snap.hashtags.join(", "),
                      visual_direction: snap.visual_direction,
                      format_recommendation: snap.format_recommendation,
                    });
                  }
                }}
                disabled={saving}
                style={{
                  padding: "10px 20px",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--surface)",
                  cursor: "pointer",
                }}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: "10px 24px",
                  border: 0,
                  borderRadius: "var(--radius-sm)",
                  background: "var(--gradient-primary)",
                  color: "var(--primary-foreground)",
                  cursor: saving ? "not-allowed" : "pointer",
                  fontWeight: 600,
                  opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? "Guardando..." : "Guardar cambios"}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              style={{
                padding: "10px 24px",
                border: 0,
                borderRadius: "var(--radius-sm)",
                background: "var(--gradient-primary)",
                color: "var(--primary-foreground)",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              Editar contenido
            </button>
          )}
        </div>
      </div>
      <section
        style={{ marginTop: 24 }}
        aria-labelledby="version-history-title"
      >
        <h2 id="version-history-title" style={{ fontSize: "1rem" }}>
          Historial de versiones
        </h2>
        {versions.length ? (
          <ol style={{ color: "var(--muted-foreground)", paddingLeft: 20 }}>
            {versions.map((version, index) => (
              <li
                key={version.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                <span>
                  Versión {version.version_number}
                  {version.user_edited ? " · editada" : " · generada"}
                  {index === 0 ? " · actual" : ""}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    handleRestore(version.id, version.version_number)
                  }
                  disabled={
                    index === 0 || editing || restoringVersionId !== null
                  }
                  aria-label={`Restaurar versión ${version.version_number}`}
                  style={{
                    padding: "4px 8px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--surface)",
                    color: "var(--foreground)",
                    cursor:
                      index === 0 || editing || restoringVersionId !== null
                        ? "not-allowed"
                        : "pointer",
                    opacity:
                      index === 0 || editing || restoringVersionId !== null
                        ? 0.6
                        : 1,
                  }}
                >
                  {restoringVersionId === version.id
                    ? "Restaurando..."
                    : "Restaurar"}
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p style={{ color: "var(--muted-foreground)" }}>
            Este proyecto aún no tiene versiones editables.
          </p>
        )}
      </section>
    </main>
    </AppShell>
  );
}

function Field({
  label,
  value,
  onChange,
  editing,
  multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  editing: boolean;
  multiline?: boolean;
}) {
  return (
    <div>
      <label
        style={{
          display: "block",
          fontSize: "0.8rem",
          fontWeight: 700,
          color: "var(--muted-foreground)",
          marginBottom: 4,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </label>
      {editing ? (
        multiline ? (
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            rows={4}
            style={{
              display: "block",
              width: "100%",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "10px 12px",
              font: "inherit",
              background: "var(--input)",
              color: "var(--foreground)",
            }}
          />
        ) : (
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "10px 12px",
              font: "inherit",
              background: "var(--input)",
              color: "var(--foreground)",
            }}
          />
        )
      ) : (
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{value}</p>
      )}
    </div>
  );
}
