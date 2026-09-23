from __future__ import annotations

from copy import deepcopy

from app.providers.vision import CANVA_FORMAT_TERMS, canva_search_url

# --------------------------------------------------------------------------- #
# Canva browse catalog
#
# These entries are not database rows and never become one: they open Canva's
# own listing so a user with no project yet still sees something to start from.
# They carry no editable slots, so nothing downstream can try to autofill them.
# --------------------------------------------------------------------------- #

#: Our template format vocabulary mapped onto the format-scoped Canva listings
#: declared in :data:`app.providers.vision.CANVA_FORMAT_TERMS`.
_CANVA_FORMAT_BY_FORMAT = {
    "static_post": "instagram_post",
    "story": "instagram_story",
}

#: Aspect ratio each format is laid out at, so the web can size a cover.
_ASPECT_BY_FORMAT = {
    "static_post": "4:5",
    "story": "9:16",
}

#: One row per catalog entry. ``cover`` is the niche token the web turns into a
#: designed CSS cover; there is no bitmap for these, so it is what the card
#: draws instead of a thumbnail.
_CATALOG_SEED: tuple[dict, ...] = (
    {
        "id": "canva_gastronomy_post",
        "cover": "gastronomy",
        "format": "static_post",
        "title": "Menú del día para restaurantes",
        "description": "Post 4:5 para mostrar platillos y precios del día.",
        "terms": ["restaurante", "menu", "comida", "promocion"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_fashion_post",
        "cover": "fashion",
        "format": "static_post",
        "title": "Nueva colección de ropa",
        "description": "Post 4:5 para anunciar prendas recién llegadas.",
        "terms": ["moda", "ropa", "coleccion", "tienda"],
        "category": "launch",
        "objective": "launch",
    },
    {
        "id": "canva_beauty_post",
        "cover": "beauty",
        "format": "static_post",
        "title": "Promoción de salón de belleza",
        "description": "Post 4:5 para ofertas de belleza, spa y cuidado personal.",
        "terms": ["belleza", "salon", "spa", "promocion"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_fitness_post",
        "cover": "fitness",
        "format": "static_post",
        "title": "Planes y rutinas de gimnasio",
        "description": "Post 4:5 para presentar membresías y rutinas de entrenamiento.",
        "terms": ["gimnasio", "fitness", "entrenamiento", "plan"],
        "category": "community",
        "objective": "engagement",
    },
    {
        "id": "canva_health_post",
        "cover": "health",
        "format": "static_post",
        "title": "Servicios de salud y bienestar",
        "description": "Post 4:5 para consultas, clínicas y campañas de bienestar.",
        "terms": ["salud", "clinica", "consulta", "bienestar"],
        "category": "brand_awareness",
        "objective": "brand_awareness",
    },
    {
        "id": "canva_technology_post",
        "cover": "technology",
        "format": "static_post",
        "title": "Servicio técnico y tecnología",
        "description": "Post 4:5 para reparaciones, soporte y productos digitales.",
        "terms": ["tecnologia", "servicio tecnico", "reparacion", "digital"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_education_post",
        "cover": "education",
        "format": "static_post",
        "title": "Inscripciones a cursos",
        "description": "Post 4:5 para academias, clases y talleres con fecha de inicio.",
        "terms": ["curso", "academia", "clases", "inscripcion"],
        "category": "launch",
        "objective": "launch",
    },
    {
        "id": "canva_real_estate_post",
        "cover": "real_estate",
        "format": "static_post",
        "title": "Propiedad en venta o alquiler",
        "description": "Post 4:5 para publicar casas, apartamentos y locales.",
        "terms": ["inmobiliaria", "casa", "venta", "propiedad"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_automotive_post",
        "cover": "automotive",
        "format": "static_post",
        "title": "Taller y venta de vehículos",
        "description": "Post 4:5 para servicios automotrices y ofertas de vehículos.",
        "terms": ["automotriz", "taller", "auto", "servicio"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_travel_post",
        "cover": "travel",
        "format": "static_post",
        "title": "Paquete de viaje",
        "description": "Post 4:5 para tours, hoteles y paquetes turísticos.",
        "terms": ["viaje", "turismo", "paquete", "hotel"],
        "category": "promotion",
        "objective": "sales",
    },
    {
        "id": "canva_events_post",
        "cover": "events",
        "format": "static_post",
        "title": "Invitación a un evento",
        "description": "Post 4:5 para invitar con fecha, hora y lugar visibles.",
        "terms": ["evento", "invitacion", "fiesta", "celebracion"],
        "category": "community",
        "objective": "store_visits",
    },
    {
        "id": "canva_pets_post",
        "cover": "pets",
        "format": "static_post",
        "title": "Servicios para mascotas",
        "description": "Post 4:5 para veterinarias, peluquería canina y tiendas de mascotas.",
        "terms": ["mascotas", "veterinaria", "perros", "cuidado"],
        "category": "community",
        "objective": "engagement",
    },
    {
        "id": "canva_gastronomy_story",
        "cover": "gastronomy",
        "format": "story",
        "title": "Historia con la oferta del día",
        "description": "Historia 9:16 para anunciar la promoción de hoy.",
        "terms": ["restaurante", "oferta", "historia", "comida"],
        "category": "promotion",
        "objective": "store_visits",
    },
    {
        "id": "canva_fashion_story",
        "cover": "fashion",
        "format": "story",
        "title": "Historia de nueva colección",
        "description": "Historia 9:16 para mostrar prendas y estilo de marca.",
        "terms": ["moda", "ropa", "historia", "estilo"],
        "category": "brand_awareness",
        "objective": "brand_awareness",
    },
    {
        "id": "canva_fitness_story",
        "cover": "fitness",
        "format": "story",
        "title": "Historia de reto fitness",
        "description": "Historia 9:16 para retos, rutinas y avances del gimnasio.",
        "terms": ["gimnasio", "reto", "fitness", "historia"],
        "category": "community",
        "objective": "engagement",
    },
    {
        "id": "canva_travel_story",
        "cover": "travel",
        "format": "story",
        "title": "Historia de destino turístico",
        "description": "Historia 9:16 para inspirar con un destino y su itinerario.",
        "terms": ["viaje", "destino", "turismo", "historia"],
        "category": "brand_awareness",
        "objective": "reach",
    },
)


def _build_entry(seed: dict) -> dict:
    fmt = seed["format"]
    return {
        "id": seed["id"],
        "title": seed["title"],
        "platforms": ["instagram"],
        "formats": [fmt],
        "category": seed["category"],
        "objective": seed["objective"],
        # No bitmap exists for a catalog entry; the web draws the cover instead.
        "thumbnail_url": None,
        "canva_url": canva_search_url(seed["terms"], fmt=_CANVA_FORMAT_BY_FORMAT[fmt]),
        "aspect_ratio": _ASPECT_BY_FORMAT[fmt],
        # These open a Canva listing rather than a fillable design, so the
        # studio must never be handed slots it cannot resolve.
        "editable_slots": [],
        "description": seed["description"],
        "source": "canva",
        "cover": seed["cover"],
    }


# A format with no listing behind it would silently degrade to the generic
# /templates/ search, which is exactly the mismatch the format paths exist to
# prevent, so it fails here instead of shipping a bad link.
_MISSING_PATHS = sorted(set(_CANVA_FORMAT_BY_FORMAT.values()) - set(CANVA_FORMAT_TERMS))
if _MISSING_PATHS:
    raise RuntimeError(f"Canva format paths missing: {', '.join(_MISSING_PATHS)}")

CANVA_CATALOG: tuple[dict, ...] = tuple(_build_entry(seed) for seed in _CATALOG_SEED)


def _matches(
    entry: dict,
    *,
    platform: str | None,
    format: str | None,
    category: str | None,
    objective: str | None,
    search: str | None,
) -> bool:
    """Mirror the filters ``list_templates`` runs in SQL.

    ``platforms`` and ``formats`` are stored as a serialized list there and
    matched with a case-insensitive LIKE, so a substring hit on any element is
    the equivalent here; category and objective are exact.
    """
    if platform and not any(platform.lower() in item.lower() for item in entry["platforms"]):
        return False
    if format and not any(format.lower() in item.lower() for item in entry["formats"]):
        return False
    if category and entry["category"] != category:
        return False
    if objective and entry["objective"] != objective:
        return False
    return not search or search.lower() in entry["title"].lower()


def list_canva_templates(
    *,
    platform: str | None = None,
    format: str | None = None,
    category: str | None = None,
    objective: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """Return the catalog entries matching the same filters as the DB listing."""
    return [
        deepcopy(entry)
        for entry in CANVA_CATALOG
        if _matches(
            entry,
            platform=platform,
            format=format,
            category=category,
            objective=objective,
            search=search,
        )
    ]


def get_canva_template(template_id: str) -> dict | None:
    """Return one catalog entry, or ``None`` when the id is not ours."""
    for entry in CANVA_CATALOG:
        if entry["id"] == template_id:
            return deepcopy(entry)
    return None
