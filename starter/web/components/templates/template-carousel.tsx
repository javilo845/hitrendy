"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

export interface TemplateCarouselItem {
  id: string;
  title: string;
  thumbnailUrl: string;
  aspectRatio: string; // e.g. "4 / 5" or "9 / 16"
  badge?: string; // category label shown over the image
  reason?: string; // one-line rationale from the recommender
}

export function TemplateCarousel(props: {
  items: TemplateCarouselItem[];
  label: string; // aria-label of the carousel group
  useLabel: string; // text of the per-card action button
  busyLabel: string; // text of that button while busy
  previousLabel: string; // aria-label of the ‹ button
  nextLabel: string; // aria-label of the › button
  onSelect: (id: string) => void;
  busyId?: string | null; // id whose button shows busyLabel and is disabled
}): JSX.Element {
  const {
    items,
    label,
    useLabel,
    busyLabel,
    previousLabel,
    nextLabel,
    onSelect,
    busyId,
  } = props;

  const trackRef = useRef<HTMLDivElement | null>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(true);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) {
      return;
    }

    function updateEdges() {
      if (!track) {
        return;
      }
      const { scrollLeft, scrollWidth, clientWidth } = track;
      setAtStart(scrollLeft <= 1);
      setAtEnd(scrollLeft >= scrollWidth - clientWidth - 1);
    }

    updateEdges();

    track.addEventListener("scroll", updateEdges, { passive: true });
    window.addEventListener("resize", updateEdges);

    return () => {
      track.removeEventListener("scroll", updateEdges);
      window.removeEventListener("resize", updateEdges);
    };
  }, [items]);

  if (items.length === 0) {
    return <></>;
  }

  function scrollByStep(direction: 1 | -1) {
    const track = trackRef.current;
    if (!track) {
      return;
    }
    const firstCard = track.querySelector<HTMLElement>(
      ".template-carousel-card"
    );
    const cardWidth = firstCard
      ? firstCard.getBoundingClientRect().width
      : track.clientWidth;
    const trackStyles = window.getComputedStyle(track);
    const gap =
      parseFloat(trackStyles.columnGap || trackStyles.gap || "0") || 0;
    const step = cardWidth + gap;
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    track.scrollBy({
      left: step * direction,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }

  return (
    <section
      className="template-carousel"
      role="group"
      aria-roledescription="carrusel"
      aria-label={label}
    >
      <button
        type="button"
        className="template-carousel-arrow template-carousel-arrow--previous"
        aria-label={previousLabel}
        onClick={() => scrollByStep(-1)}
        disabled={atStart}
      >
        <span aria-hidden="true">‹</span>
      </button>

      <div className="template-carousel-track" ref={trackRef}>
        {items.map((item) => (
          <TemplateCarouselCard
            key={item.id}
            item={item}
            useLabel={useLabel}
            busyLabel={busyLabel}
            busyId={busyId}
            onSelect={onSelect}
          />
        ))}
      </div>

      <button
        type="button"
        className="template-carousel-arrow template-carousel-arrow--next"
        aria-label={nextLabel}
        onClick={() => scrollByStep(1)}
        disabled={atEnd}
      >
        <span aria-hidden="true">›</span>
      </button>
    </section>
  );
}

function TemplateCarouselCard({
  item,
  useLabel,
  busyLabel,
  busyId,
  onSelect,
}: {
  item: TemplateCarouselItem;
  useLabel: string;
  busyLabel: string;
  busyId?: string | null;
  onSelect: (id: string) => void;
}) {
  const [failed, setFailed] = useState(false);
  const isBusy = busyId === item.id;

  return (
    <article className="template-carousel-card">
      <div
        className="template-carousel-media"
        style={{ aspectRatio: item.aspectRatio }}
      >
        {failed ? (
          <div
            className="template-thumbnail-fallback"
            role="img"
            aria-label={item.title}
          >
            <span aria-hidden="true">HT</span>
            <small>{item.title}</small>
          </div>
        ) : (
          <Image
            src={item.thumbnailUrl}
            alt={item.title}
            fill
            onError={() => setFailed(true)}
            sizes="(max-width: 639px) 60vw, 14rem"
          />
        )}
        {item.badge ? (
          <span className="template-carousel-badge">{item.badge}</span>
        ) : null}
      </div>
      <h3>{item.title}</h3>
      {item.reason ? (
        <p className="template-carousel-reason">{item.reason}</p>
      ) : null}
      <button
        type="button"
        onClick={() => onSelect(item.id)}
        disabled={busyId != null}
      >
        {isBusy ? busyLabel : useLabel} <span aria-hidden="true">→</span>
      </button>
    </article>
  );
}
