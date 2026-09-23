"use client";

import { useRouter } from "next/navigation";
import { Fragment, useState } from "react";

import { saveFirstPrompt } from "@/lib/creation-draft";
import { loginPath, routes } from "@/lib/routes";

const examples = [
  "Lanzamiento de cafetería",
  "Post para tienda de ropa",
  "Presentar un producto",
];

export function HeroComposer() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");

  function start() {
    if (prompt.trim()) saveFirstPrompt(prompt);
    router.push(loginPath(routes.studioNew));
  }

  return (
    <Fragment>
      <div className="hero-composer">
        <label className="visually-hidden" htmlFor="landing-prompt">
          Describe qué quieres crear para tu negocio
        </label>
        <textarea
          id="landing-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Describe qué quieres crear para tu negocio..."
          rows={3}
        />
        <div className="hero-composer-actions">
          <div className="hero-composer-tools" aria-label="Opciones de contenido">
            <button type="button" aria-label="Adjuntar archivo">⌕ <span>Adjuntar</span></button>
            <button type="button" aria-label="Agregar imagen">▧ <span>Imagen</span></button>
          </div>
          <button type="button" className="button-primary" onClick={start}>
            Comenzar <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
      <div className="prompt-examples" aria-label="Ideas de ejemplo">
        {examples.map((example) => (
          <button key={example} type="button" onClick={() => setPrompt(example)}>
            {example}
          </button>
        ))}
      </div>
    </Fragment>
  );
}
