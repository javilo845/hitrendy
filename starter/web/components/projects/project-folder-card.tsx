"use client";

import Link from "next/link";
import { useId } from "react";
import type { AppLocale } from "@/lib/i18n";
import { appCopy, formatDate } from "@/lib/i18n";

export interface ProjectItem {
  id: string;
  name: string;
  platform: string;
  status: "active" | "archived";
  updated_at: string | null;
  artifact_snapshot?: { hook?: string } | null;
}

interface ProjectFolderCardProps {
  project: ProjectItem;
  variant?: "blue" | "purple";
  locale: AppLocale;
  isBusy?: boolean;
  onStatusChange: (project: ProjectItem) => void;
}

export function ProjectFolderCard({
  project,
  variant = "blue",
  locale,
  isBusy = false,
  onStatusChange,
}: ProjectFolderCardProps) {
  const titleId = useId();
  const copy = appCopy[locale];
  const isPurple = variant === "purple";

  const glowColor = isPurple
    ? "rgba(180, 130, 250, 0.45)"
    : "rgba(45, 90, 245, 0.45)";

  return (
    <article
      className="project-folder-card-wrapper"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        position: "relative",
      }}
    >
      {/* Opening a folder starts a brief: the guided flow loads this project as
          its context, so every visit produces a fresh draft instead of parking
          the user in the editor. The saved version stays one click away. */}
      <Link
        href={`/studio/new?project=${encodeURIComponent(project.id)}&brief=1`}
        className="project-folder-link"
        style={{
          textDecoration: "none",
          color: "inherit",
          display: "flex",
          flexDirection: "column",
        }}
        aria-labelledby={titleId}
      >
        <div
          className={`project-folder-art ${isPurple ? "project-folder-art--purple" : "project-folder-art--blue"}`}
          style={{
            position: "relative",
            width: "100%",
            aspectRatio: "1.4 / 1",
            minHeight: "140px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "all 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)",
            filter: `drop-shadow(0 14px 24px ${glowColor})`,
          }}
        >
          {/* Custom 3D SVG Folder matching user visual reference */}
          <svg
            viewBox="0 0 240 160"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{
              width: "100%",
              height: "100%",
              overflow: "visible",
              display: "block",
            }}
          >
            <defs>
              {/* Blue Gradients */}
              <linearGradient id={`folderBlueBack-${project.id}`} x1="0" y1="0" x2="240" y2="160" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#1e3ebb" />
                <stop offset="100%" stopColor="#152c96" />
              </linearGradient>
              <linearGradient id={`folderBlueFront-${project.id}`} x1="0" y1="30" x2="0" y2="155" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#3b62f6" />
                <stop offset="50%" stopColor="#294ce8" />
                <stop offset="100%" stopColor="#1d3bb9" />
              </linearGradient>
              <linearGradient id={`folderBlueGlow-${project.id}`} x1="0" y1="140" x2="240" y2="155" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.8" />
                <stop offset="50%" stopColor="#93c5fd" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#60a5fa" stopOpacity="0.8" />
              </linearGradient>

              {/* Purple Gradients */}
              <linearGradient id={`folderPurpleBack-${project.id}`} x1="0" y1="0" x2="240" y2="160" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#8b5cf6" />
                <stop offset="100%" stopColor="#6d28d9" />
              </linearGradient>
              <linearGradient id={`folderPurpleFront-${project.id}`} x1="0" y1="30" x2="0" y2="155" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#c084fc" />
                <stop offset="50%" stopColor="#ab6cf8" />
                <stop offset="100%" stopColor="#9333ea" />
              </linearGradient>
              <linearGradient id={`folderPurpleGlow-${project.id}`} x1="0" y1="140" x2="240" y2="155" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#e9d5ff" stopOpacity="0.8" />
                <stop offset="50%" stopColor="#f3e8ff" stopOpacity="0.9" />
                <stop offset="100%" stopColor="#e9d5ff" stopOpacity="0.8" />
              </linearGradient>

              {/* Top rim highlight */}
              <linearGradient id={`rimHighlight-${project.id}`} x1="0" y1="0" x2="240" y2="0" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity="0.1" />
              </linearGradient>
            </defs>

            {/* Back Flap / Tab */}
            <path
              d="M 12 36 
                 C 12 24, 20 16, 32 16 
                 L 80 16 
                 C 92 16, 100 24, 108 36 
                 L 220 36 
                 C 230 36, 236 44, 236 54 
                 L 236 142 
                 C 236 150, 230 156, 220 156 
                 L 20 156 
                 C 12 156, 4 150, 4 142 
                 L 4 48 
                 C 4 40, 10 36, 12 36 Z"
              fill={isPurple ? `url(#folderPurpleBack-${project.id})` : `url(#folderBlueBack-${project.id})`}
            />

            {/* Paper peeking inside */}
            <rect
              x="24"
              y="26"
              width="192"
              height="80"
              rx="8"
              fill="rgba(255, 255, 255, 0.12)"
              stroke="rgba(255, 255, 255, 0.2)"
              strokeWidth="1"
            />

            {/* Front Pocket / Main body */}
            <rect
              x="6"
              y="40"
              width="228"
              height="112"
              rx="18"
              fill={isPurple ? `url(#folderPurpleFront-${project.id})` : `url(#folderBlueFront-${project.id})`}
              stroke={`url(#rimHighlight-${project.id})`}
              strokeWidth="1.5"
            />

            {/* Glass reflection streak on front flap */}
            <path
              d="M 12 44 L 110 44 C 120 44, 124 50, 116 64 L 32 144 C 24 152, 12 148, 12 140 Z"
              fill="rgba(255, 255, 255, 0.08)"
            />

            {/* Bottom luminous glow accent line */}
            <rect
              x="20"
              y="148"
              width="200"
              height="3"
              rx="1.5"
              fill={isPurple ? `url(#folderPurpleGlow-${project.id})` : `url(#folderBlueGlow-${project.id})`}
            />
          </svg>

          {/* Project count / status pill on folder */}
          <div
            style={{
              position: "absolute",
              bottom: "16px",
              right: "18px",
              padding: "2px 8px",
              borderRadius: "12px",
              background: "rgba(0, 0, 0, 0.4)",
              backdropFilter: "blur(4px)",
              color: "#ffffff",
              fontSize: "0.7rem",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              gap: "4px",
              border: "1px solid rgba(255, 255, 255, 0.15)",
            }}
          >
            <span>{project.platform === "instagram" ? "📸" : "📱"}</span>
            <span>{project.artifact_snapshot?.hook ? "1 post" : "Borrador"}</span>
          </div>
        </div>

        {/* Project Metadata below folder */}
        <div style={{ marginTop: "0.85rem", padding: "0 0.25rem" }}>
          <h2
            id={titleId}
            style={{
              margin: "0 0 0.25rem",
              fontSize: "0.95rem",
              fontWeight: 700,
              color: "#ffffff",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              letterSpacing: "-0.01em",
            }}
            title={project.name}
          >
            {project.name}
          </h2>
          <p
            style={{
              margin: 0,
              fontSize: "0.75rem",
              color: "#94a3b8",
              display: "flex",
              alignItems: "center",
              gap: "0.35rem",
            }}
          >
            <span>{project.platform}</span>
            <span>·</span>
            <span>{formatDate(locale, project.updated_at) || copy.dashboard.noActivity}</span>
          </p>
        </div>
      </Link>

      {/* Archive / Restore Button */}
      <div style={{ marginTop: "0.5rem", display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
        <Link
          href={`/projects/${encodeURIComponent(project.id)}`}
          className="project-folder-edit"
          style={{
            padding: "0.3rem 0.65rem",
            fontSize: "0.72rem",
            borderRadius: "6px",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            color: "#cbd5e1",
            textDecoration: "none",
          }}
        >
          {copy.common.edit}
        </Link>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onStatusChange(project);
          }}
          disabled={isBusy}
          style={{
            padding: "0.3rem 0.65rem",
            fontSize: "0.72rem",
            borderRadius: "6px",
            background: "rgba(255, 255, 255, 0.05)",
            color: "#cbd5e1",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            cursor: isBusy ? "not-allowed" : "pointer",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(255, 255, 255, 0.12)";
            e.currentTarget.style.color = "#ffffff";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(255, 255, 255, 0.05)";
            e.currentTarget.style.color = "#cbd5e1";
          }}
        >
          {isBusy
            ? copy.common.saving
            : project.status === "active"
              ? copy.dashboard.archive
              : copy.dashboard.restore}
        </button>
      </div>
    </article>
  );
}

interface NewProjectFolderCardProps {
  locale: AppLocale;
}

export function NewProjectFolderCard({ locale }: NewProjectFolderCardProps) {
  const copy = appCopy[locale];

  return (
    <Link
      href="/studio/new"
      className="project-folder-card-wrapper project-folder-new-card"
      style={{
        display: "flex",
        flexDirection: "column",
        textDecoration: "none",
        color: "inherit",
      }}
    >
      <div
        className="project-folder-new-art"
        style={{
          position: "relative",
          width: "100%",
          aspectRatio: "1.4 / 1",
          minHeight: "140px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "18px",
          background: "rgba(30, 27, 75, 0.35)",
          border: "2px solid rgba(168, 85, 247, 0.35)",
          backdropFilter: "blur(12px)",
          transition: "all 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)",
          boxShadow: "0 8px 24px rgba(126, 34, 206, 0.15)",
        }}
      >
        {/* Big clean plus matching image reference */}
        <span
          style={{
            fontSize: "4rem",
            fontWeight: 300,
            lineHeight: 1,
            color: "#c084fc",
            textShadow: "0 0 16px rgba(192, 132, 252, 0.6)",
            transition: "transform 0.25s ease",
          }}
        >
          +
        </span>
      </div>

      <div style={{ marginTop: "0.85rem", padding: "0 0.25rem" }}>
        <h2
          style={{
            margin: "0 0 0.25rem",
            fontSize: "0.95rem",
            fontWeight: 700,
            color: "#ffffff",
          }}
        >
          {copy.dashboard.newProject}
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: "0.75rem",
            color: "#94a3b8",
          }}
        >
          {copy.dashboard.newProjectHint}
        </p>
      </div>
    </Link>
  );
}
