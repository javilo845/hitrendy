import Link from "next/link";
import Image from "next/image";

import { LandingPosterRail } from "@/components/landing/poster-rail";
import { AboutCollage } from "@/components/landing/about-collage";
import { PublicHeader } from "@/components/layout/public-header";
import { routes } from "@/lib/routes";

export default function HomePage() {
  return (
    <main className="landing-page">
      <PublicHeader />

      <section
        id="inicio"
        className="landing-hero"
        aria-labelledby="hero-title"
      >
        <div className="landing-hero-inner">
          <h1 id="hero-title">Comienza a Crear</h1>
          <LandingPosterRail />
          <Link className="landing-cta" href={routes.login}>
            <Image
              src="/brand/hitrendy-mark.svg"
              alt=""
              aria-hidden="true"
              width={27}
              height={27}
            />
            <span>Empezar a Crear</span>
          </Link>
        </div>
        <svg
          className="landing-hero-scribble"
          viewBox="0 0 150 120"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M7 110c-8-29 6-52 29-52 18 0 25 17 13 29-15 15-38 3-35-20 3-24 25-45 58-43"
            stroke="currentColor"
            strokeWidth="8"
            strokeLinecap="round"
          />
        </svg>
      </section>

      <section
        id="quienes-somos"
        className="landing-about"
        aria-labelledby="about-title"
      >
        <svg
          className="landing-about-stroke"
          viewBox="0 0 480 260"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M18 242C65 78 220-12 452 26"
            stroke="currentColor"
            strokeWidth="18"
            strokeLinecap="round"
          />
          <path
            d="M86 258C134 128 267 57 474 82"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
          />
        </svg>
        <svg
          className="landing-about-mark"
          viewBox="0 0 430 430"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M310 60c-85 0-156 67-156 150 0 62 46 113 104 113 43 0 72-31 61-65-11-34-56-43-76-15-20 28 10 72 55 57 59-20 90-96 62-157"
            stroke="currentColor"
            strokeWidth="18"
            strokeLinecap="round"
          />
          <path
            d="M253 185c12 18 34 25 54 17"
            stroke="currentColor"
            strokeWidth="15"
            strokeLinecap="round"
          />
        </svg>
        <div className="landing-about-inner">
          <div className="landing-about-visual">
            <AboutCollage />
          </div>
          <div className="landing-about-copy">
            <h2 id="about-title">¿Quiénes somos?</h2>
            <p>
              HiTrendy es una plataforma diseñada para ayudar a pequeños
              negocios, emprendedores y creadores a transformar sus ideas en
              contenido visual atractivo, profesional y alineado con las
              tendencias actuales usando Inteligencia Artificial.
            </p>
            <p>
              Buscamos simplificar la creación de contenido para que cualquier
              persona, sin importar su experiencia en diseño o marketing, pueda
              comunicar el valor de su negocio de manera efectiva.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
