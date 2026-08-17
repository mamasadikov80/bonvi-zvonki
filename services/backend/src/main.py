"""ZvonkiDashboard API — kirish nuqtasi."""

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.exceptions import AppError

# Barcha ORM modellar import qilinishi shart — Alembic ularni
# metadata orqali topadi. Tartib muhim emas.
from src.modules.agents.infrastructure import models as _agents  # noqa: F401
from src.modules.agents.presentation.router import router as agents_router
from src.modules.analytics.presentation.router import router as analytics_router
from src.modules.auth.presentation.router import router as auth_router
from src.modules.calls.infrastructure import models as _calls  # noqa: F401
from src.modules.calls.presentation.router import router as calls_router
from src.modules.clients.infrastructure import models as _clients  # noqa: F401
from src.modules.groups.infrastructure import models as _groups  # noqa: F401
from src.modules.groups.presentation.router import router as groups_router
from src.modules.pipeline.infrastructure import models as _pipeline  # noqa: F401
from src.modules.pipeline.presentation.router import router as pipeline_router
from src.modules.regions.infrastructure import models as _regions  # noqa: F401
from src.modules.regions.presentation.router import router as regions_router
from src.modules.scoring.infrastructure import models as _scoring  # noqa: F401
from src.modules.scoring.infrastructure import rubric_models as _rubric  # noqa: F401
from src.modules.scoring.presentation.router import router as rubric_router
from src.modules.settings.infrastructure import models as _settings  # noqa: F401
from src.modules.settings.presentation.router import router as settings_router
from src.modules.surveys.infrastructure import models as _surveys  # noqa: F401
from src.modules.surveys.presentation.router import router as surveys_router
from src.modules.users.infrastructure import models as _users  # noqa: F401
from src.modules.users.presentation.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Savdo xodimlarini AI orqali baholash platformasi.\n\n"
        "**Rollar:** `admin` · `manager` · `sales` · `viewer`"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI ning inglizcha `detail` javobini loyiha konvertiga keltiradi.

    So'rovnoma endpointlari ochiq — xatoni bevosita client ko'radi,
    shuning uchun xabar o'zbekcha va tushunarli bo'lishi kerak.
    """
    first = exc.errors()[0] if exc.errors() else {}
    # loc = ("body", "csat") — foydalanuvchiga maydon nomini ko'rsatamiz
    field = ".".join(str(part) for part in first.get("loc", ())[1:]) or "so'rov"
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": f"«{field}» maydoni noto'g'ri to'ldirilgan",
                "detail": jsonable_encoder(exc.errors()),
            }
        },
    )


# Yuklangan fayllar (avatar va h.k.)
MEDIA_ROOT = Path("/app/media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
# Ba'zi tizimlarda .webp mimetypes ro'yxatida yo'q — brauzer to'g'ri tanishi uchun
mimetypes.add_type("image/webp", ".webp")
app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")


@app.get("/health", tags=["System"], summary="Servis holati")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.APP_NAME}


# ── Marshrutlar ───────────────────────────────────────────────
api = settings.API_V1_PREFIX

app.include_router(auth_router, prefix=api)
app.include_router(users_router, prefix=api)
app.include_router(agents_router, prefix=api)
app.include_router(calls_router, prefix=api)
app.include_router(analytics_router, prefix=api)
app.include_router(rubric_router, prefix=api)
app.include_router(surveys_router, prefix=api)
app.include_router(groups_router, prefix=api)
app.include_router(regions_router, prefix=api)
app.include_router(settings_router, prefix=api)
app.include_router(pipeline_router, prefix=api)
