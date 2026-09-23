"""Single import point that registers every ORM mapping.

A process that maps only part of the schema cannot resolve a foreign key into
the tables it never imported: ``claim_next_job`` fails with
``NoReferencedTableError`` on ``image_generation_jobs.workspace_id`` even though
the database itself is perfectly healthy. The web app never hits this because
its router wiring happens to import everything; a standalone worker imports only
its own domain, so it needs the mappings named explicitly.

Import this module for its side effect before opening a session in any entry
point that is not the FastAPI app.
"""

from __future__ import annotations

from app.assets import models as asset_models  # noqa: F401
from app.business import models as business_models  # noqa: F401
from app.conversations import models as conversation_models  # noqa: F401
from app.identity import models as identity_models  # noqa: F401
from app.images import models as image_models  # noqa: F401
from app.operations import models as operations_models  # noqa: F401
from app.projects import models as project_models  # noqa: F401
from app.social import models as social_models  # noqa: F401
from app.templates import models as template_models  # noqa: F401
from app.trends import models as trend_models  # noqa: F401
from app.videos import models as video_models  # noqa: F401
