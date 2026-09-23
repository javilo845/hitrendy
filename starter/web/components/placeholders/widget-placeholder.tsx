import type { CSSProperties } from "react";

type WidgetPlaceholderProps = {
  aspectRatio?: string;
  minHeight?: number | string;
  borderRadius?: number | string;
  className?: string;
  label?: string;
  animated?: boolean;
};

export function WidgetPlaceholder({
  aspectRatio,
  minHeight,
  borderRadius,
  className,
  label,
  animated = true,
}: WidgetPlaceholderProps) {
  const style = {
    ...(aspectRatio ? { aspectRatio } : {}),
    ...(minHeight ? { minHeight } : {}),
    ...(borderRadius ? { borderRadius } : {}),
  } satisfies CSSProperties;

  return (
    <div
      className={`widget-placeholder${animated ? " widget-placeholder--animated" : ""}${className ? ` ${className}` : ""}`}
      style={style}
      aria-label={label}
      role={label ? "img" : undefined}
    >
      {label ? <span className="widget-placeholder-label">{label}</span> : null}
    </div>
  );
}

export function HeroMediaPlaceholder() {
  return (
    <WidgetPlaceholder
      className="placeholder-hero-media"
      aspectRatio="16 / 10"
      label="Espacio para el recurso visual principal"
    />
  );
}

export function TemplateCardPlaceholder({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <article
      className={`template-placeholder${compact ? " template-placeholder--compact" : ""}`}
      aria-label="Plantilla pendiente de recursos de diseño"
    >
      <WidgetPlaceholder
        className="template-placeholder-media"
        aspectRatio="4 / 5"
      />
      <div className="template-placeholder-copy">
        <WidgetPlaceholder minHeight="1rem" />
        <WidgetPlaceholder
          minHeight="0.8rem"
          className="placeholder-line-short"
        />
      </div>
    </article>
  );
}

export function LogoPlaceholder() {
  return (
    <WidgetPlaceholder
      className="logo-placeholder"
      aspectRatio="1"
      label="Logo pendiente"
    />
  );
}

export function IllustrationPlaceholder() {
  return (
    <WidgetPlaceholder
      className="illustration-placeholder"
      aspectRatio="4 / 3"
      label="Ilustración pendiente"
    />
  );
}

export function ProjectThumbnailPlaceholder() {
  return (
    <WidgetPlaceholder
      className="project-thumbnail-placeholder"
      aspectRatio="16 / 9"
      label="Miniatura del proyecto pendiente"
    />
  );
}

export function StudioPreviewPlaceholder() {
  return (
    <WidgetPlaceholder
      className="studio-preview-placeholder"
      aspectRatio="4 / 3"
      label="Vista previa pendiente"
    />
  );
}
