import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { SupportEmail } from "@/components/legal/support-email";
import { routes } from "@/lib/routes";

export default function TermsPage() {
  return (
    <main className="auth-page auth-page--single">
      <article className="auth-card legal-page" aria-labelledby="terms-title">
        <div className="auth-brand"><Logo /></div>
        <p className="eyebrow">TÉRMINOS · 2026-08-02</p>
        <h1 id="terms-title">Términos de la beta cerrada</h1>
        <p>HiTrendy ayuda a crear borradores editables para redes sociales. Tú revisas y decides qué publicar; la beta no publica contenido automáticamente.</p>
        <h2>Uso responsable</h2>
        <p>No uses el servicio para spam, acoso, fraude, contenido ilegal ni para intentar acceder a datos de otra cuenta. Podemos limitar o bloquear el acceso cuando exista abuso.</p>
        <h2>Disponibilidad</h2>
        <p>La beta puede tener cold starts, límites de proveedores y ventanas de mantenimiento. No afirmamos un SLA ni resultados garantizados de marketing.</p>
        <h2>Contacto y cambios</h2>
        <p>Las preguntas de soporte se atienden en <SupportEmail />. Informaremos cambios relevantes en esta página.</p>
        <p><Link href={routes.privacy}>Leer privacidad</Link> · <Link href={routes.login}>Volver</Link></p>
      </article>
    </main>
  );
}
