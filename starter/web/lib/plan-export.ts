import type { AdvisorData } from "@/components/advisor-response-card";

const PRIORITY_LABELS: Record<string, string> = {
  high: "Alta prioridad",
  medium: "Media prioridad",
  low: "Sugerencia",
};

/**
 * Everything below is model output rendered as a document, so it is escaped
 * before it reaches any markup rather than trusted for being ours.
 */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function planFileName(date = new Date()): string {
  const iso = Number.isNaN(date.getTime())
    ? new Date().toISOString()
    : date.toISOString();
  return `plan-de-contenido-${iso.slice(0, 10)}`;
}

/**
 * A standalone print document. It carries its own styles because it is printed
 * from an isolated frame: nothing from the app's stylesheet reaches it, which
 * is also what keeps the sheet readable in black on white regardless of the
 * theme the user is looking at.
 */
export function buildPlanDocument(
  advisor: AdvisorData,
  { title = "Plan de contenido", date = new Date() }: { title?: string; date?: Date } = {}
): string {
  const printed = Number.isNaN(date.getTime()) ? new Date() : date;
  const stamp = printed.toLocaleDateString("es", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const recommendations = (advisor.recommendations || [])
    .map(
      (item) => `
      <li class="item">
        <p class="item-head">
          <strong>${escapeHtml(item.title)}</strong>
          <span class="tag">${escapeHtml(
            PRIORITY_LABELS[item.priority] || PRIORITY_LABELS.medium
          )}</span>
        </p>
        <p class="item-body">${escapeHtml(item.description)}</p>
      </li>`
    )
    .join("");

  const actions = (advisor.next_actions || [])
    .map((action) => `<li>${escapeHtml(action)}</li>`)
    .join("");

  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(planFileName(printed))}</title>
<style>
  @page { margin: 18mm; }
  body { margin: 0; color: #14121f; background: #ffffff;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 11pt; }
  header { border-bottom: 2px solid #541787; padding-bottom: 10px; margin-bottom: 18px; }
  h1 { margin: 0 0 4px; font-size: 20pt; color: #541787; }
  .stamp { margin: 0; font-size: 9pt; color: #55506b; }
  h2 { margin: 22px 0 8px; font-size: 12pt; text-transform: uppercase;
       letter-spacing: 0.06em; color: #55506b; }
  p { line-height: 1.5; }
  ul { margin: 0; padding: 0; list-style: none; }
  ol { margin: 0; padding-left: 1.2em; line-height: 1.7; }
  .item { border: 1px solid #ddd8ec; border-radius: 6px; padding: 10px 12px;
          margin-bottom: 8px; page-break-inside: avoid; }
  .item-head { display: flex; justify-content: space-between; gap: 10px; margin: 0 0 4px; }
  .item-body { margin: 0; font-size: 10pt; color: #35304a; }
  .tag { font-size: 8pt; font-weight: 700; white-space: nowrap; color: #541787; }
  footer { margin-top: 24px; border-top: 1px solid #ddd8ec; padding-top: 8px;
           font-size: 8pt; color: #7b7590; }
</style>
</head>
<body>
  <header>
    <h1>${escapeHtml(title)}</h1>
    <p class="stamp">Generado el ${escapeHtml(stamp)} · HiTrendy</p>
  </header>
  <h2>Estrategia recomendada</h2>
  <p>${escapeHtml(advisor.summary || "")}</p>
  ${recommendations ? `<h2>Ideas y publicaciones de la semana</h2><ul>${recommendations}</ul>` : ""}
  ${actions ? `<h2>Próximos pasos</h2><ol>${actions}</ol>` : ""}
  <footer>Plan generado por el asistente de HiTrendy. Revisa los datos antes de publicar.</footer>
</body>
</html>`;
}

/**
 * Prints the plan from a detached frame, which is what turns it into a PDF:
 * every browser's print dialog can save to a file, and doing it this way needs
 * no PDF dependency and no popup the browser might block.
 */
export function printPlan(
  advisor: AdvisorData,
  options?: { title?: string; date?: Date }
): void {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.style.opacity = "0";
  document.body.appendChild(frame);

  const doc = frame.contentDocument;
  const view = frame.contentWindow;
  if (!doc || !view) {
    frame.remove();
    return;
  }

  doc.open();
  doc.write(buildPlanDocument(advisor, options));
  doc.close();

  const cleanUp = () => {
    // Deferred: removing the frame while its print dialog is closing cancels
    // the job in some browsers.
    window.setTimeout(() => frame.remove(), 1000);
  };

  view.addEventListener("afterprint", cleanUp, { once: true });
  view.focus();
  view.print();
  // Safari never fires `afterprint` from a frame, so the frame is reclaimed on
  // a timer as well; both paths are idempotent.
  window.setTimeout(cleanUp, 60_000);
}
