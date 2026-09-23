"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { Logo } from "@/components/brand/logo";
import { api } from "@/lib/api";
import { routes } from "@/lib/routes";
import {
  appCopy,
  isSupportedLocale,
  readStoredLocale,
  type AppLocale,
} from "@/lib/i18n";

type IconName =
  "studio" | "dashboard" | "trends" | "templates" | "settings" | "logout" | "bell";
type NavItem = { href: string; label: string; icon: IconName };

function navigationFor(copy: ReturnType<typeof getCopy>): NavItem[] {
  return [
    { href: routes.studioNew, label: copy.nav.studio, icon: "studio" },
    { href: routes.dashboard, label: copy.nav.dashboard, icon: "dashboard" },
    { href: routes.trends, label: copy.nav.trends, icon: "trends" },
    { href: routes.templates, label: copy.nav.templates, icon: "templates" },
    { href: routes.settings, label: copy.nav.settings, icon: "settings" },
  ];
}

function getCopy(locale: AppLocale) {
  return appCopy[locale];
}

function AppIcon({ name }: { name: IconName }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "studio")
    return (
      <svg {...common}>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
      </svg>
    );
  if (name === "dashboard")
    return (
      <svg {...common}>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </svg>
    );
  if (name === "trends")
    return (
      <svg {...common}>
        <path d="M4 18 9 12l4 3 7-9" />
        <path d="M15 6h5v5" />
      </svg>
    );
  if (name === "templates")
    return (
      <svg {...common}>
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <path d="M8 3v18M3 9h18" />
      </svg>
    );
  if (name === "settings")
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3.5" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34A1.7 1.7 0 0 0 14 20.92V21h-4v-.08a1.7 1.7 0 0 0-1.03-1.52 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.52-1.03H3v-4h.08A1.7 1.7 0 0 0 4.6 8.94a1.7 1.7 0 0 0-.34-1.88L4.2 7l2.83-2.83.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 10 3.08V3h4v.08a1.7 1.7 0 0 0 1.03 1.52 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 7l-.06.06a1.7 1.7 0 0 0-.34 1.88A1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" />
      </svg>
    );
  if (name === "bell")
    return (
      <svg {...common}>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        <path d="M10 21h4" />
      </svg>
    );
  return (
    <svg {...common}>
      <path d="M10 17l5-5-5-5" />
      <path d="M15 12H3" />
      <path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" />
    </svg>
  );
}

function isCurrentPath(pathname: string, href: string) {
  if (href === routes.home) return pathname === href;
  if (href === routes.studioNew) return pathname.startsWith("/studio");
  return pathname === href || pathname.startsWith(`${href}/`);
}

function sectionLabel(pathname: string, copy: ReturnType<typeof getCopy>) {
  if (pathname.startsWith("/studio")) return copy.nav.studio;
  if (pathname.startsWith("/dashboard")) return copy.nav.dashboard;
  if (pathname.startsWith("/trends")) return copy.nav.trends;
  if (pathname.startsWith("/templates")) return copy.nav.templates;
  if (pathname.startsWith("/settings")) return copy.nav.settings;
  if (pathname.startsWith("/onboarding")) return copy.nav.dashboard;
  return "HiTrendy";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [locale, setLocale] = useState<AppLocale>(readStoredLocale);
  const copy = appCopy[locale];
  const navigation = navigationFor(copy);
  useEffect(() => {
    const onLocale = (event: Event) => {
      const next = (event as CustomEvent<AppLocale>).detail;
      if (isSupportedLocale(next)) setLocale(next);
    };
    window.addEventListener("hitrendy:locale", onLocale);
    return () => window.removeEventListener("hitrendy:locale", onLocale);
  }, []);

  async function logout() {
    setLoggingOut(true);
    try {
      await api.auth.logout();
    } finally {
      router.replace(routes.home);
      router.refresh();
    }
  }

  return (
    <ProtectedRoute>
      <div className="app-shell" data-theme="dark-shell">
        <aside className="app-sidebar" aria-label={copy.nav.main}>
          <Link
            href={routes.home}
            className="brand-lockup"
            aria-label={copy.nav.home}
          >
            <Logo inverse />
          </Link>
          <nav className="desktop-nav" aria-label={copy.nav.sections}>
            {navigation.map((item) => {
              const current = isCurrentPath(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="nav-link"
                  aria-current={current ? "page" : undefined}
                  data-active={current || undefined}
                  data-label={item.label}
                >
                  <span className="nav-mark">
                    <AppIcon name={item.icon} />
                  </span>
                  <span className="nav-label">{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="sidebar-footer">
            <button
              type="button"
              className="nav-link nav-link-button"
              data-label={copy.nav.logout}
              onClick={logout}
              disabled={loggingOut}
            >
              <span className="nav-mark">
                <AppIcon name="logout" />
              </span>
              <span className="nav-label">
                {loggingOut ? copy.nav.loggingOut : copy.nav.logout}
              </span>
            </button>
          </div>
        </aside>

        <div className="app-main">
          <header className="app-topbar">
            <div className="app-breadcrumb">
              <span>HiTrendy</span>
              <b aria-hidden="true">›</b>
              <strong>{sectionLabel(pathname, copy)}</strong>
            </div>
            <div className="top-actions">
              <button
                type="button"
                className="top-icon-button"
                aria-label={copy.nav.notifications}
              >
                <AppIcon name="bell" />
              </button>
              <button type="button" className="profile-button">
                <span>Hi, Trendy</span>
                <b>HT</b>
              </button>
            </div>
          </header>
          <div className="app-content">{children}</div>
        </div>

        <nav className="mobile-nav" aria-label={copy.nav.mobile}>
          {navigation.map((item) => {
            const current = isCurrentPath(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="mobile-nav-link"
                aria-current={current ? "page" : undefined}
                data-active={current || undefined}
              >
                <AppIcon name={item.icon} />
                <span>{item.label}</span>
              </Link>
            );
          })}
          <button
            type="button"
            className="mobile-nav-link mobile-nav-button"
            onClick={logout}
            disabled={loggingOut}
          >
            <AppIcon name="logout" />
            <span>
              {loggingOut ? copy.nav.loggingOut : copy.nav.mobileLogout}
            </span>
          </button>
        </nav>
      </div>
    </ProtectedRoute>
  );
}
