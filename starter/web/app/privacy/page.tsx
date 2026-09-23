import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { SupportEmail } from "@/components/legal/support-email";
import { routes } from "@/lib/routes";

export default function PrivacyPage() {
  return (
    <main className="auth-page auth-page--single">
      <article className="auth-card legal-page" aria-labelledby="privacy-title">
        <div className="auth-brand"><Logo /></div>
        <p className="eyebrow">POLÍTICA · 2026-08-02</p>
        <h1 id="privacy-title">Privacidad</h1>
        <p>HiTrendy guarda los datos de tu cuenta, negocio, marca, proyectos y archivos necesarios para prestar el servicio.</p>
        <h2>Uso de los datos</h2>
        <p>Usamos proveedores configurados por el servicio para autenticación, almacenamiento y generación. No vendemos tus datos ni mostramos tus credenciales al navegador.</p>
        <h2>Retención y eliminación</h2>
        <p>Conservamos la información mientras la cuenta esté activa. Puedes solicitar su eliminación desde Configuración; el acceso se revoca de inmediato y la purga se procesa de forma asíncrona.</p>
        <h2>Contacto</h2>
        <p>Para preguntas de privacidad, escribe a <SupportEmail />.</p>
        <p><Link href={routes.terms}>Leer términos</Link> · <Link href={routes.login}>Volver</Link></p>
      </article>
    </main>
  );
}
