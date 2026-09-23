const form = document.querySelector("#composer");
const input = document.querySelector("#message");
const conversation = document.querySelector("#conversation");

const business = {
  name: "Café Central",
  category: "Gastronomía",
  city: "Tegucigalpa",
  primary_product: "una bebida fría de café",
  target_audience: "estudiantes universitarios",
  platform: "instagram",
  objective: "store_visits",
  tone: "youthful"
};

function addMessage(text, role) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  article.innerHTML = `<div class="message-label">${role === "user" ? "Tú" : "HiTrendy"}</div><p></p>`;
  article.querySelector("p").textContent = text;
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
  return article;
}

function addArtifact(data) {
  const article = document.createElement("article");
  article.className = "message artifact-card";
  article.innerHTML = `
    <div class="message-label">PROPUESTA GENERADA</div>
    <h3>${escapeHtml(data.hook)}</h3>
    <div class="artifact-grid">
      <div class="artifact-section"><strong>Texto</strong><span>${escapeHtml(data.caption)}</span></div>
      <div class="artifact-section"><strong>Llamado a la acción</strong><span>${escapeHtml(data.call_to_action)}</span></div>
      <div class="artifact-section"><strong>Dirección visual</strong><span>${escapeHtml(data.visual_direction)}</span></div>
      <div class="artifact-section"><strong>Formato y etiquetas</strong><span>${escapeHtml(data.format_recommendation)} · ${data.hashtags.map(escapeHtml).join(" ")}</span></div>
    </div>
    <div class="artifact-actions">
      <button class="primary-action" type="button">Guardar proyecto</button>
      <button class="secondary-action copy-action" type="button">Copiar texto</button>
      <button class="secondary-action variation-action" type="button">Más corto</button>
    </div>`;
  article.querySelector(".copy-action").addEventListener("click", async () => {
    await navigator.clipboard.writeText(`${data.hook}\n\n${data.caption}\n\n${data.call_to_action}\n${data.hashtags.join(" ")}`);
    article.querySelector(".copy-action").textContent = "Copiado";
  });
  article.querySelector(".variation-action").addEventListener("click", () => {
    input.value = "Haz una versión más corta manteniendo el objetivo de visitas al local";
    input.focus();
  });
  article.querySelector(".primary-action").addEventListener("click", () => {
    article.querySelector(".primary-action").textContent = "Proyecto guardado";
  });
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
}

async function generate(text) {
  addMessage(text, "user");
  const pending = addMessage("Preparando una propuesta para tu negocio…", "assistant");
  try {
    const response = await fetch("/api/demo/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, business})
    });
    const body = await response.json();
    pending.remove();
    if (!response.ok) throw new Error(body.detail || "No se pudo generar el contenido.");
    addArtifact(body);
  } catch (error) {
    pending.querySelector("p").textContent = error.message;
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  generate(text);
});

document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt;
    input.focus();
  });
});
