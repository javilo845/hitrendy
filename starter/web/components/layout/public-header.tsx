"use client";

import Link from "next/link";
import { Logo } from "@/components/brand/logo";
import { routes } from "@/lib/routes";

export function PublicHeader() {
  return (
    <header className="public-header">
      <Link
        href={routes.home}
        className="public-brand"
        aria-label="HiTrendy, inicio"
      >
        <Logo />
      </Link>
      <nav className="public-nav" aria-label="Navegación pública">
        <Link className="public-start-link" href={routes.login}>
          Empezar a Crear
        </Link>
        <a href="#quienes-somos">Quiénes somos</a>
      </nav>
    </header>
  );
}
