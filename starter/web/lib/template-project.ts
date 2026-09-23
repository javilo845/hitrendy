import { api, ApiError } from "@/lib/api";

export class MissingBusinessError extends Error {
  constructor() {
    super("Completa los datos de tu negocio antes de usar una plantilla.");
    this.name = "MissingBusinessError";
  }
}

export interface CreatedTemplateProject {
  id: string;
  artifact_id?: string | null;
  source_template_id?: string | null;
}

export async function createProjectFromTemplate(
  templateId: string
): Promise<CreatedTemplateProject> {
  const businesses = await api.businesses.list();
  const business = businesses[0];
  if (!business || typeof business.id !== "string") {
    throw new MissingBusinessError();
  }

  const project = await api.projects.create({
    template_id: templateId,
    business_id: business.id,
  });

  if (typeof project.id !== "string") {
    throw new ApiError(
      502,
      "INVALID_PROJECT_RESPONSE",
      "No recibimos el proyecto creado. Inténtalo de nuevo.",
      true
    );
  }

  return project as unknown as CreatedTemplateProject;
}
