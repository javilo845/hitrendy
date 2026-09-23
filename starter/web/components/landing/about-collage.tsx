"use client";

import Image from "next/image";
import { useState } from "react";

export interface AboutCollageImages {
  centerHero?: string;
  topLeft?: string;
  bottomLeft?: string;
  topRight?: string;
}

export interface AboutCollageBadges {
  heroUser?: string;
  heroTag?: string;
  heroAudio?: string;
  reactionText?: string;
}

interface AboutCollageProps {
  images?: AboutCollageImages;
  badges?: AboutCollageBadges;
  className?: string;
}

const DEFAULT_IMAGES: Required<AboutCollageImages> = {
  centerHero: "/landing/about-coffee.jpg",
  topLeft: "/landing/about-korean.jpg",
  bottomLeft: "/landing/about-burger.png",
  topRight: "/landing/about-toast.jpg",
};

const DEFAULT_BADGES: Required<AboutCollageBadges> = {
  heroUser: "goodgood_coffeebar",
  heroTag: "Supplies",
  heroAudio: "solangeeferreira · Original audio (may...",
  reactionText: "Love it! Going to try it out.",
};

export function AboutCollage({
  images = {},
  badges = {},
  className = "",
}: AboutCollageProps) {
  const mergedImages = { ...DEFAULT_IMAGES, ...images };
  const mergedBadges = { ...DEFAULT_BADGES, ...badges };

  const [activeHover, setActiveHover] = useState<string | null>(null);

  return (
    <div
      className={`about-collage-container ${className}`}
      style={{
        position: "relative",
        width: "100%",
        maxWidth: "560px",
        aspectRatio: "1.05 / 1",
        margin: "0 auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* 1. Top-Left Card (Korean Meal / Photo Frame) */}
      <div
        className="about-card about-card--top-left"
        onMouseEnter={() => setActiveHover("topLeft")}
        onMouseLeave={() => setActiveHover(null)}
        style={{
          position: "absolute",
          top: "6%",
          left: "0%",
          width: "35%",
          aspectRatio: "0.88 / 1",
          borderRadius: "18px",
          overflow: "hidden",
          boxShadow: "0 16px 36px -6px rgba(0, 0, 0, 0.55)",
          border: "2px solid rgba(255, 255, 255, 0.12)",
          zIndex: activeHover === "topLeft" ? 6 : 1,
          transition: "transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease",
          transform: activeHover === "topLeft" ? "scale(1.08) translateY(-6px)" : "scale(1)",
        }}
      >
        <Image
          src={mergedImages.topLeft}
          alt="Fotografía de producto y comida para redes sociales"
          fill
          sizes="(max-width: 768px) 140px, 200px"
          style={{ objectFit: "cover" }}
          priority
        />
      </div>

      {/* 2. Bottom-Left Card (Burger Lab Bold Flavor) */}
      <div
        className="about-card about-card--bottom-left"
        onMouseEnter={() => setActiveHover("bottomLeft")}
        onMouseLeave={() => setActiveHover(null)}
        style={{
          position: "absolute",
          bottom: "4%",
          left: "3%",
          width: "35%",
          aspectRatio: "0.92 / 1",
          borderRadius: "18px",
          overflow: "hidden",
          boxShadow: "0 16px 36px -6px rgba(0, 0, 0, 0.55)",
          border: "2px solid rgba(255, 255, 255, 0.12)",
          zIndex: activeHover === "bottomLeft" ? 6 : 1,
          transition: "transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease",
          transform: activeHover === "bottomLeft" ? "scale(1.08) translateY(-6px)" : "scale(1)",
        }}
      >
        <Image
          src={mergedImages.bottomLeft}
          alt="Diseño publicitario gastronómico y hamburguesería"
          fill
          sizes="(max-width: 768px) 140px, 200px"
          style={{ objectFit: "cover" }}
          priority
        />
      </div>

      {/* 3. Top-Right Card (Faloé Cosmetics Toasties - tilted per Figma design) */}
      <div
        className="about-card about-card--top-right"
        onMouseEnter={() => setActiveHover("topRight")}
        onMouseLeave={() => setActiveHover(null)}
        style={{
          position: "absolute",
          top: "10%",
          right: "0%",
          width: "36%",
          aspectRatio: "0.85 / 1",
          borderRadius: "16px",
          overflow: "hidden",
          boxShadow: "0 16px 36px -6px rgba(0, 0, 0, 0.55)",
          border: "2px solid rgba(255, 255, 255, 0.15)",
          zIndex: activeHover === "topRight" ? 6 : 1,
          transition: "transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease",
          transform: activeHover === "topRight" ? "scale(1.08) translateY(-6px) rotate(6deg)" : "rotate(6.5deg)",
          transformOrigin: "center center",
        }}
      >
        <Image
          src={mergedImages.topRight}
          alt="Publicación de producto y estética visual editorial"
          fill
          sizes="(max-width: 768px) 140px, 210px"
          style={{ objectFit: "cover" }}
          priority
        />
      </div>

      {/* 4. Center Hero Card (Good Good Coffeebar Instagram Story) */}
      <div
        className="about-card about-card--center-hero"
        onMouseEnter={() => setActiveHover("hero")}
        onMouseLeave={() => setActiveHover(null)}
        style={{
          position: "relative",
          width: "56%",
          aspectRatio: "0.82 / 1",
          borderRadius: "22px",
          overflow: "hidden",
          boxShadow: "0 28px 56px -12px rgba(0, 0, 0, 0.75), 0 0 0 1px rgba(255, 255, 255, 0.15)",
          border: "2px solid rgba(255, 255, 255, 0.2)",
          zIndex: activeHover === "hero" || !activeHover ? 4 : 3,
          transition: "transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.35s ease",
          transform: activeHover === "hero" ? "scale(1.04) translateY(-4px)" : "scale(1)",
        }}
      >
        {/* Background Image */}
        <Image
          src={mergedImages.centerHero}
          alt="Contenido principal para cafetería con diseño profesional"
          fill
          sizes="(max-width: 768px) 260px, 340px"
          style={{ objectFit: "cover" }}
          priority
        />

        {/* Top Story Header matching Figma */}
        <div
          style={{
            position: "absolute",
            top: "12px",
            left: "12px",
            right: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 2,
          }}
        >
          {/* User badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <div
              style={{
                width: "26px",
                height: "26px",
                borderRadius: "50%",
                background: "#ffffff",
                display: "grid",
                placeItems: "center",
                fontSize: "12px",
                boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
              }}
            >
              ☕
            </div>
            <span
              style={{
                fontSize: "0.82rem",
                fontWeight: 700,
                color: "#ffffff",
                textShadow: "0 2px 4px rgba(0,0,0,0.8)",
                letterSpacing: "-0.01em",
              }}
            >
              {mergedBadges.heroUser}
            </span>
          </div>

          {/* Top-Right Video icon */}
          <div
            style={{
              width: "20px",
              height: "20px",
              display: "grid",
              placeItems: "center",
              color: "rgba(255, 255, 255, 0.8)",
              fontSize: "0.75rem",
              textShadow: "0 1px 3px rgba(0,0,0,0.8)",
            }}
          >
            ▶
          </div>
        </div>

        {/* Tag Pill badge in center top */}
        <div
          style={{
            position: "absolute",
            top: "42px",
            right: "24%",
            zIndex: 2,
            display: "flex",
            alignItems: "center",
            gap: "5px",
            padding: "5px 14px",
            background: "rgba(235, 230, 255, 0.95)",
            backdropFilter: "blur(6px)",
            borderRadius: "30px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
          }}
        >
          <span style={{ fontSize: "0.75rem" }}>🧃</span>
          <span
            style={{
              color: "#321a72",
              fontSize: "0.74rem",
              fontWeight: 700,
            }}
          >
            {mergedBadges.heroTag}
          </span>
        </div>

        {/* Bottom Audio Tag */}
        <div
          style={{
            position: "absolute",
            bottom: "10px",
            left: "12px",
            right: "12px",
            zIndex: 2,
            display: "flex",
            alignItems: "center",
            gap: "6px",
            color: "rgba(255, 255, 255, 0.95)",
            fontSize: "0.72rem",
            fontWeight: 500,
            textShadow: "0 2px 4px rgba(0,0,0,0.9)",
            background: "linear-gradient(to top, rgba(0,0,0,0.65), transparent)",
            padding: "10px 6px 2px",
          }}
        >
          <span>🎵</span>
          <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {mergedBadges.heroAudio}
          </span>
        </div>
      </div>

      {/* 5. Floating Reaction Pill (overlapping bottom right of center hero) */}
      <div
        style={{
          position: "absolute",
          bottom: "14%",
          right: "2%",
          zIndex: 5,
          display: "flex",
          alignItems: "center",
          gap: "8px",
          background: "#ffffff",
          padding: "10px 18px",
          borderRadius: "9999px",
          boxShadow: "0 14px 32px rgba(0, 0, 0, 0.4)",
          color: "#1e1b4b",
          fontSize: "0.78rem",
          fontWeight: 700,
          border: "1px solid rgba(255, 255, 255, 0.8)",
          animation: "floatSlow 4s ease-in-out infinite",
        }}
      >
        <span style={{ fontSize: "1.1rem", lineHeight: 1 }}>❤️</span>
        <span>{mergedBadges.reactionText}</span>
      </div>
    </div>
  );
}
