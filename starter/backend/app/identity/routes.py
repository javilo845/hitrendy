from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.repository import (
    brand_profile_to_dict,
    business_to_dict,
    create_business,
    upsert_brand_profile,
)
from app.core.config import settings
from app.core.cookies import (
    OAUTH_COOKIE,
    SIGNUP_COOKIE,
    delete_csrf_cookie,
    delete_oauth_cookie,
    delete_session_cookie,
    delete_signup_cookie,
    read_oauth_cookie,
    set_csrf_cookie,
    set_oauth_cookie,
    set_session_cookie,
    set_signup_cookie,
)
from app.core.csrf import (
    CSRF_CONTEXT_SIGNUP,
    _generate_csrf_token,
    _pick_context,
)
from app.core.errors import AppError, ForbiddenError
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.domain.models import Category, Objective, Platform, Tone
from app.identity.account_deletion import (
    STATUS_TOKEN_MAX_LENGTH,
    STATUS_TOKEN_MIN_LENGTH,
    STATUS_TOKEN_PATTERN,
    confirmation_phrase,
    read_public_deletion_status,
)
from app.identity.account_deletion import (
    request_account_deletion as apply_account_deletion,
)
from app.identity.google_oauth import (
    GoogleIdentity,
    GoogleOIDCClient,
    GoogleOIDCError,
    create_code_challenge,
)
from app.identity.models import (
    AuthSession,
    OAuthAccount,
    OAuthAuthorizationRequest,
    PendingSignup,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)
from app.identity.password_reset import (
    PASSWORD_RESET_MESSAGE,
    confirm_password_reset,
    request_password_reset,
)
from app.identity.passwords import hash_password, verify_password
from app.operations.invites import redeem_invite, resolve_invite
from app.operations.models import BetaInvite
from app.services.usage_policy import usage_limit_snapshot

router = APIRouter(prefix="/auth", tags=["identity"])

GOOGLE_PROVIDER = "google"
SIGNUP_TTL = timedelta(hours=24)
USAGE_PERIOD_DAYS = 30
SignupStep = Literal["business", "channels", "brand", "review"]
InterfaceLocale = Literal["es", "en", "pt"]


def _hash_password(password: str, salt: bytes | None = None) -> str:
    return hash_password(password, salt)


def _verify_password(password: str, encoded: str) -> bool:
    return verify_password(password, encoded)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _datetime_is_expired(value: datetime) -> bool:
    expires_at = value if value.tzinfo else value.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


def _load_draft(pending: PendingSignup) -> dict[str, object]:
    try:
        payload = json.loads(pending.draft_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_signup_step(draft: dict[str, object]) -> SignupStep:
    if "business" not in draft:
        return "business"
    if "channels" not in draft:
        return "channels"
    if "brand" not in draft:
        return "brand"
    return "review"


def _signup_response(pending: PendingSignup) -> dict[str, object]:
    return {
        "signup": {
            "status": "completed" if pending.completed_at else "pending",
            "current_step": pending.current_step,
            "expires_at": pending.expires_at.isoformat(),
            "updated_at": pending.updated_at.isoformat() if pending.updated_at else None,
            "version": pending.version,
            "draft": _load_draft(pending),
        }
    }


async def _create_session(db: AsyncSession, user_id: str) -> str:
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        )
    )
    await db.flush()
    return token


async def _reject_authenticated_signup(
    db: AsyncSession, session_token: str | None
) -> None:
    if not session_token:
        return
    session = (
        await db.execute(
            select(AuthSession).where(AuthSession.token_hash == _token_hash(session_token))
        )
    ).scalar_one_or_none()
    if session is not None and not _datetime_is_expired(session.expires_at):
        raise AppError(
            "ALREADY_AUTHENTICATED",
            "Ya tienes una sesión activa.",
            status_code=409,
        )





def get_google_oidc_client() -> GoogleOIDCClient:
    return GoogleOIDCClient(settings)


def _google_callback_redirect(path: str, *, outcome: str | None = None) -> RedirectResponse:
    query = f"?{urlencode({'oauth': outcome})}" if outcome else ""
    response = RedirectResponse(f"{settings.frontend_url}{path}{query}", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    delete_oauth_cookie(response)
    return response


def _google_callback_error(outcome: str) -> RedirectResponse:
    return _google_callback_redirect("/login", outcome=outcome)


async def _get_pending_signup(
    db: AsyncSession,
    token: str | None,
    *,
    lock: bool = False,
) -> PendingSignup:
    if not token:
        raise AppError("SIGNUP_NOT_FOUND", "No encontramos un registro pendiente.", status_code=404)
    statement = select(PendingSignup).where(PendingSignup.token_hash == _token_hash(token))
    if lock:
        statement = statement.with_for_update()
    pending = (await db.execute(statement)).scalar_one_or_none()
    if pending is None:
        raise AppError("SIGNUP_NOT_FOUND", "No encontramos un registro pendiente.", status_code=404)
    if pending.completed_at is None and _datetime_is_expired(pending.expires_at):
        await db.delete(pending)
        await db.commit()
        raise AppError("SIGNUP_EXPIRED", "El registro pendiente expiró.", status_code=410)
    return pending


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    workspace_name: str = Field(min_length=1, max_length=120)
    invite_code: str | None = Field(None, min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)


class UpdateAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interface_locale: InterfaceLocale


class DeleteAccountRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=64)
    # The client generates the opaque status token so a retried request recovers
    # the same job. Only its hash is ever persisted.
    status_token: str = Field(
        min_length=STATUS_TOKEN_MIN_LENGTH,
        max_length=STATUS_TOKEN_MAX_LENGTH,
        pattern=STATUS_TOKEN_PATTERN,
    )


class SignupStartRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    interface_locale: InterfaceLocale = "es"
    invite_code: str | None = Field(None, min_length=12, max_length=128)


class SignupBusinessDraft(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Category
    country: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    primary_product: str = Field(min_length=1, max_length=240)
    target_audience: str = Field(min_length=1, max_length=500)
    website_url: str | None = Field(None, max_length=500)


class SignupChannelsDraft(BaseModel):
    preferred_platforms: list[Platform] = Field(min_length=1)
    primary_objective: Objective


class SignupBrandDraft(BaseModel):
    voice_tones: list[Tone] = Field(min_length=1, max_length=3)
    value_proposition: str = Field(min_length=1, max_length=500)
    preferred_words: list[str] = Field(default_factory=list, max_length=30)
    forbidden_words: list[str] = Field(default_factory=list, max_length=30)
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    content_locale: InterfaceLocale = "es"


class SignupReviewDraft(BaseModel):
    confirmed: bool


class SignupDraftRequest(BaseModel):
    step: SignupStep
    expected_version: int = Field(ge=1)
    business: SignupBusinessDraft | None = None
    channels: SignupChannelsDraft | None = None
    brand: SignupBrandDraft | None = None
    review: SignupReviewDraft | None = None

    @model_validator(mode="after")
    def validate_step_payload(self) -> SignupDraftRequest:
        payloads = {
            "business": self.business,
            "channels": self.channels,
            "brand": self.brand,
            "review": self.review,
        }
        if payloads[self.step] is None or sum(value is not None for value in payloads.values()) != 1:
            raise ValueError("El borrador debe incluir únicamente los datos del paso indicado.")
        return self


async def _consume_google_authorization_request(
    db: AsyncSession, *, state: str
) -> tuple[OAuthAuthorizationRequest | None, str | None]:
    request = (
        await db.execute(
            select(OAuthAuthorizationRequest)
            .where(
                OAuthAuthorizationRequest.provider == GOOGLE_PROVIDER,
                OAuthAuthorizationRequest.state_hash == _token_hash(state),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if request is None:
        return None, "invalid_state"
    if _datetime_is_expired(request.expires_at):
        return None, "expired_state"
    if request.consumed_at is not None:
        return None, "used_state"
    request.consumed_at = datetime.now(UTC)
    await db.commit()
    return request, None


async def _create_or_resume_google_signup(
    db: AsyncSession, identity: GoogleIdentity
) -> str | None:
    now = datetime.now(UTC)
    existing = (
        await db.execute(
            select(PendingSignup)
            .where(
                PendingSignup.oauth_provider == GOOGLE_PROVIDER,
                PendingSignup.oauth_subject == identity.subject,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.completed_at is not None:
            return None
        if _datetime_is_expired(existing.expires_at):
            await db.delete(existing)
            await db.flush()
        else:
            token = secrets.token_urlsafe(32)
            existing.token_hash = _token_hash(token)
            existing.expires_at = now + SIGNUP_TTL
            await db.commit()
            return token

    if (
        await db.execute(select(User).where(User.email == identity.email))
    ).scalar_one_or_none() is not None:
        return None
    if (
        await db.execute(select(PendingSignup).where(PendingSignup.email_normalized == identity.email))
    ).scalar_one_or_none() is not None:
        return None

    token = secrets.token_urlsafe(32)
    pending = PendingSignup(
        email_normalized=identity.email,
        name=identity.name,
        oauth_provider=GOOGLE_PROVIDER,
        oauth_subject=identity.subject,
        interface_locale="es",
        token_hash=_token_hash(token),
        expires_at=now + SIGNUP_TTL,
    )
    db.add(pending)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(PendingSignup).where(
                    PendingSignup.oauth_provider == GOOGLE_PROVIDER,
                    PendingSignup.oauth_subject == identity.subject,
                )
            )
        ).scalar_one_or_none()
        if existing is None or existing.completed_at is not None or _datetime_is_expired(existing.expires_at):
            return None
        token = secrets.token_urlsafe(32)
        existing.token_hash = _token_hash(token)
        existing.expires_at = datetime.now(UTC) + SIGNUP_TTL
        await db.commit()
    return token


@router.post("/register", status_code=201, deprecated=True)
async def register(
    body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    email = body.email.casefold().strip()
    invite: BetaInvite | None = None
    if settings.beta_invites_enabled:
        if not body.invite_code:
            raise AppError(
                "BETA_INVITE_REQUIRED",
                "Esta beta requiere una invitación.",
                status_code=403,
            )
        invite = await resolve_invite(db, code=body.invite_code, email=email, lock=True)
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise AppError("EMAIL_IN_USE", "No se pudo crear la cuenta.", status_code=409)
    user = User(email=email, name=body.name.strip(), password_hash=_hash_password(body.password))
    workspace = Workspace(name=body.workspace_name.strip())
    db.add_all([user, workspace])
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    if invite is not None:
        await redeem_invite(db, invite)
    token = await _create_session(db, user.id)
    await db.commit()
    set_session_cookie(response, token)
    delete_signup_cookie(response)
    delete_csrf_cookie(response)
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "workspace": {"id": workspace.id, "name": workspace.name, "role": "owner"},
    }


@router.post("/password-reset/request", status_code=202)
async def request_password_reset_endpoint(
    body: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Start recovery without revealing whether the address exists."""

    await request_password_reset(
        db,
        email=body.email,
        requested_ip=request.client.host if request.client else None,
    )
    return {"message": PASSWORD_RESET_MESSAGE}


@router.post("/password-reset/confirm")
async def confirm_password_reset_endpoint(
    body: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await confirm_password_reset(db, token=body.token, password=body.password)
    return {"status": "reset"}


@router.get("/google/status")
async def google_sign_in_status() -> dict[str, bool]:
    return {"configured": settings.google_sign_in_configured}


@router.get("/google/start")
async def start_google_sign_in(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not settings.google_sign_in_configured:
        raise AppError(
            "GOOGLE_SIGN_IN_UNAVAILABLE",
            "El acceso con Google no está disponible en este momento.",
            status_code=503,
        )
    now = datetime.now(UTC)
    await db.execute(delete(OAuthAuthorizationRequest).where(OAuthAuthorizationRequest.expires_at <= now))
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    db.add(
        OAuthAuthorizationRequest(
            provider=GOOGLE_PROVIDER,
            state_hash=_token_hash(state),
            nonce=nonce,
            expires_at=now + timedelta(seconds=settings.google_oauth_state_ttl_seconds),
        )
    )
    await db.commit()
    set_oauth_cookie(response, state=state, code_verifier=code_verifier)
    response.headers["Cache-Control"] = "no-store"
    return {
        "authorization_url": get_google_oidc_client().authorization_url(
            state=state,
            code_challenge=create_code_challenge(code_verifier),
            nonce=nonce,
        )
    }


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_cookie: str | None = Cookie(None, alias=OAUTH_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not settings.google_sign_in_configured:
        return _google_callback_error("unavailable")
    cookie_state = read_oauth_cookie(oauth_cookie)
    if state is None or cookie_state is None or not hmac.compare_digest(state, cookie_state[0]):
        return _google_callback_error("invalid_state")
    authorization_request, state_error = await _consume_google_authorization_request(db, state=state)
    if authorization_request is None:
        return _google_callback_error(state_error or "invalid_state")
    if error:
        return _google_callback_error("cancelled")
    if not code:
        return _google_callback_error("failed")

    try:
        oidc_client = get_google_oidc_client()
        id_token = await oidc_client.exchange_code(code=code, code_verifier=cookie_state[1])
        identity = await oidc_client.validate_id_token(
            id_token=id_token, nonce=authorization_request.nonce
        )
    except GoogleOIDCError as exc:
        print(f"[GOOGLE_OAUTH] callback exception: code={exc.code}", flush=True)
        outcome = "unavailable" if exc.code == "GOOGLE_OAUTH_UNAVAILABLE" else "failed"
        return _google_callback_error(outcome)

    linked = (
        await db.execute(
            select(OAuthAccount, User)
            .join(User, User.id == OAuthAccount.user_id)
            .where(
                OAuthAccount.provider == GOOGLE_PROVIDER,
                OAuthAccount.provider_subject == identity.subject,
            )
            .with_for_update()
        )
    ).one_or_none()
    if linked is not None:
        account, user = linked
        if user.status != "active":
            return _google_callback_error("unavailable")
        account.last_login_at = datetime.now(UTC)
        token = await _create_session(db, user.id)
        await db.commit()
        response = _google_callback_redirect("/dashboard")
        set_session_cookie(response, token)
        delete_signup_cookie(response)
        delete_csrf_cookie(response)
        return response

    signup_token = await _create_or_resume_google_signup(db, identity)
    if signup_token is None:
        return _google_callback_error("account_exists")
    response = _google_callback_redirect("/onboarding")
    set_signup_cookie(response, signup_token)
    csrf_token = _generate_csrf_token(signup_token, CSRF_CONTEXT_SIGNUP)
    set_csrf_cookie(response, csrf_token)
    return response


@router.post("/signup/start", status_code=201)
async def start_signup(
    body: SignupStartRequest,
    response: Response,
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await _reject_authenticated_signup(db, session_token)
    now = datetime.now(UTC)
    email = body.email.casefold().strip()
    invite_id: str | None = None
    if settings.beta_invites_enabled:
        if not body.invite_code:
            raise AppError(
                "BETA_INVITE_REQUIRED",
                "Esta beta requiere una invitación.",
                status_code=403,
            )
        invite = await resolve_invite(db, code=body.invite_code, email=email)
        invite_id = invite.id
    await db.execute(
        delete(PendingSignup).where(
            PendingSignup.completed_at.is_(None), PendingSignup.expires_at <= now
        )
    )
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is not None:
        await db.rollback()
        raise AppError("EMAIL_IN_USE", "No se pudo crear la cuenta.", status_code=409)
    if (
        await db.execute(select(PendingSignup).where(PendingSignup.email_normalized == email))
    ).scalar_one_or_none() is not None:
        await db.rollback()
        raise AppError("EMAIL_IN_USE", "No se pudo crear la cuenta.", status_code=409)
    token = secrets.token_urlsafe(32)
    pending = PendingSignup(
        email_normalized=email,
        name=body.name.strip(),
        password_hash=_hash_password(body.password),
        interface_locale=body.interface_locale,
        beta_invite_id=invite_id,
        token_hash=_token_hash(token),
        expires_at=now + SIGNUP_TTL,
    )
    db.add(pending)
    await db.commit()
    await db.refresh(pending)
    set_signup_cookie(response, token)
    csrf_token = _generate_csrf_token(token, CSRF_CONTEXT_SIGNUP)
    set_csrf_cookie(response, csrf_token)
    return _signup_response(pending)


@router.get("/signup")
async def get_signup(
    signup_token: str | None = Cookie(None, alias=SIGNUP_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    pending = await _get_pending_signup(db, signup_token)
    return _signup_response(pending)


@router.patch("/signup")
async def save_signup_draft(
    body: SignupDraftRequest,
    signup_token: str | None = Cookie(None, alias=SIGNUP_COOKIE),
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    await _reject_authenticated_signup(db, session_token)
    pending = await _get_pending_signup(db, signup_token)
    if pending.completed_at is not None:
        raise AppError("SIGNUP_CONFLICT", "El registro ya fue completado.", status_code=409)
    draft = _load_draft(pending)
    payload = getattr(body, body.step)
    assert payload is not None
    proposed_draft = {**draft, body.step: payload.model_dump(exclude_none=True)}
    if body.expected_version != pending.version:
        if proposed_draft == draft:
            return _signup_response(pending)
        raise AppError("SIGNUP_CONFLICT", "El borrador fue actualizado en otra sesión.", status_code=409)
    required_step = _current_signup_step(draft)
    order = {"business": 0, "channels": 1, "brand": 2, "review": 3}
    if order[body.step] > order[required_step]:
        raise AppError("SIGNUP_INCOMPLETE", "Completa los pasos anteriores.", status_code=422)
    pending.draft_json = json.dumps(proposed_draft, ensure_ascii=False, sort_keys=True)
    pending.current_step = _current_signup_step(proposed_draft)
    pending.version += 1
    await db.commit()
    await db.refresh(pending)
    return _signup_response(pending)


@router.delete("/signup", status_code=204)
async def cancel_signup(
    response: Response,
    signup_token: str | None = Cookie(None, alias=SIGNUP_COOKIE),
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _reject_authenticated_signup(db, session_token)
    pending = await _get_pending_signup(db, signup_token)
    if pending.completed_at is not None:
        raise AppError("SIGNUP_CONFLICT", "El registro ya fue completado.", status_code=409)
    await db.delete(pending)
    await db.commit()
    delete_signup_cookie(response)
    return Response(status_code=204, headers=response.headers)


def _validated_complete_draft(
    draft: dict[str, object],
) -> tuple[SignupBusinessDraft, SignupChannelsDraft, SignupBrandDraft]:
    try:
        business = SignupBusinessDraft.model_validate(draft.get("business"))
        channels = SignupChannelsDraft.model_validate(draft.get("channels"))
        brand = SignupBrandDraft.model_validate(draft.get("brand"))
        review = SignupReviewDraft.model_validate(draft.get("review"))
    except ValidationError as exc:
        raise AppError("SIGNUP_INCOMPLETE", "Completa todos los pasos del registro.", 422) from exc
    if not review.confirmed:
        raise AppError("SIGNUP_INCOMPLETE", "Confirma los datos antes de continuar.", 422)
    return business, channels, brand


@router.post("/signup/complete")
async def complete_signup(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=255),
    signup_token: str | None = Cookie(None, alias=SIGNUP_COOKIE),
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    pending = await _get_pending_signup(db, signup_token, lock=True)
    if pending.completed_at is not None:
        if pending.completion_idempotency_key == idempotency_key:
            return json.loads(pending.completion_response_json or "{}")
        raise AppError("SIGNUP_CONFLICT", "El registro ya fue completado.", status_code=409)
    await _reject_authenticated_signup(db, session_token)
    business_draft, channels_draft, brand_draft = _validated_complete_draft(_load_draft(pending))
    try:
        invite: BetaInvite | None = None
        if settings.beta_invites_enabled:
            invite = await db.scalar(
                select(BetaInvite).where(BetaInvite.id == pending.beta_invite_id).with_for_update()
            )
            if invite is None or invite.status != "active":
                raise AppError(
                    "BETA_INVITE_INVALID",
                    "La invitación de beta ya no está disponible.",
                    status_code=403,
                )
            if invite.expires_at is not None and _datetime_is_expired(invite.expires_at):
                invite.status = "revoked"
                raise AppError(
                    "BETA_INVITE_EXPIRED",
                    "La invitación de beta expiró.",
                    status_code=403,
                )
            if invite.email_normalized and invite.email_normalized != pending.email_normalized:
                raise AppError(
                    "BETA_INVITE_INVALID",
                    "La invitación de beta no está asociada a este correo.",
                    status_code=403,
                )
        existing = await db.execute(select(User).where(User.email == pending.email_normalized))
        if existing.scalar_one_or_none() is not None:
            raise AppError("EMAIL_IN_USE", "No se pudo crear la cuenta.", status_code=409)
        user = User(
            email=pending.email_normalized,
            name=pending.name,
            password_hash=pending.password_hash or "",
            interface_locale=pending.interface_locale,
            status="active",
        )
        workspace = Workspace(name=business_draft.name)
        db.add_all([user, workspace])
        await db.flush()
        if pending.oauth_provider or pending.oauth_subject:
            if not pending.oauth_provider or not pending.oauth_subject:
                raise AppError(
                    "SIGNUP_CONFLICT",
                    "No se pudo completar el registro.",
                    status_code=409,
                )
            db.add(
                OAuthAccount(
                    user_id=user.id,
                    provider=pending.oauth_provider,
                    provider_subject=pending.oauth_subject,
                    email_at_link_time=pending.email_normalized,
                    last_login_at=datetime.now(UTC),
                )
            )
            await db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        business_data = business_draft.model_dump(exclude_none=True) | channels_draft.model_dump()
        business_data["content_locale"] = brand_draft.content_locale
        business_data["onboarding_completed_at"] = datetime.now(UTC)
        business = await create_business(db, workspace.id, business_data)
        profile = await upsert_brand_profile(
            db,
            workspace.id,
            business.id,
            brand_draft.model_dump(exclude={"content_locale"}),
        )
        db.add(UserPreference(user_id=user.id, interface_locale=pending.interface_locale))
        session_token = await _create_session(db, user.id)
        result: dict[str, object] = {
            "user": {"id": user.id, "name": user.name, "email": user.email},
            "workspace": {"id": workspace.id, "name": workspace.name, "role": "owner"},
            "business": business_to_dict(business),
            "brand_profile": brand_profile_to_dict(profile),
        }
        pending.completed_at = datetime.now(UTC)
        pending.current_step = "completed"
        if invite is not None:
            await redeem_invite(db, invite)
        pending.completion_idempotency_key = idempotency_key
        pending.completion_response_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("EMAIL_IN_USE", "No se pudo crear la cuenta.", status_code=409) from exc
    except Exception:
        await db.rollback()
        raise
    set_session_cookie(response, session_token)
    delete_signup_cookie(response)
    delete_csrf_cookie(response)
    return result


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(User).where(User.email == body.email.casefold().strip(), User.status == "active")
    )
    user = result.scalar_one_or_none()
    if user is None or not _verify_password(body.password, user.password_hash):
        raise ForbiddenError("Credenciales inválidas.")
    token = await _create_session(db, user.id)
    await db.commit()
    set_session_cookie(response, token)
    delete_signup_cookie(response)
    delete_csrf_cookie(response)
    return {"user": {"id": user.id, "name": user.name, "email": user.email}}


@router.post("/logout", status_code=204)
async def logout(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await db.execute(delete(AuthSession).where(AuthSession.id == principal.session.id))
    await db.commit()
    response = Response(status_code=204)
    delete_session_cookie(response)
    return response


@router.get("/me")
async def me(principal: CurrentPrincipal = Depends(get_current_principal), db: AsyncSession = Depends(get_db)) -> dict:
    preference = await db.get(UserPreference, principal.user["id"])
    locale = preference.interface_locale if preference else "es"
    return {
        "user": {
            **principal.user,
            "interface_locale": locale,
            # The UI must offer exactly the phrase the server accepts.
            "deletion_confirmation_phrase": confirmation_phrase(locale),
        },
        "workspaces": principal.workspaces,
    }


@router.patch("/account")
async def update_account(
    body: UpdateAccountRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, principal.user["id"])
    if user is None or user.status != "active":
        raise ForbiddenError()
    user.name = body.name.strip()
    # The email is identity, never editable here.
    user.interface_locale = body.interface_locale
    preference = await db.get(UserPreference, user.id)
    if preference is None:
        preference = UserPreference(user_id=user.id, interface_locale=body.interface_locale)
        db.add(preference)
    else:
        preference.interface_locale = body.interface_locale
    await db.commit()
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "interface_locale": preference.interface_locale,
            "deletion_confirmation_phrase": confirmation_phrase(preference.interface_locale),
        }
    }


@router.get("/usage")
async def account_usage(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Honest 30-day usage for the authorized workspace.

    A ``NULL`` reported cost is unknown, never zero, so each group reports how
    many events carried a cost and how many did not. Model identifiers and
    provider request ids are intentionally never exposed.
    """

    from app.conversations.models import AIUsageEvent

    since = datetime.now(UTC) - timedelta(days=USAGE_PERIOD_DAYS)
    rows = (
        await db.execute(
            select(
                AIUsageEvent.capability,
                AIUsageEvent.quality_level,
                AIUsageEvent.currency,
                func.count().label("generations"),
                func.sum(AIUsageEvent.total_tokens).label("total_tokens"),
                func.sum(AIUsageEvent.reported_cost).label("reported_cost"),
                func.count(AIUsageEvent.reported_cost).label("known_cost_count"),
            )
            .where(
                AIUsageEvent.workspace_id == workspace_id,
                AIUsageEvent.created_at >= since,
            )
            .group_by(
                AIUsageEvent.capability, AIUsageEvent.quality_level, AIUsageEvent.currency
            )
            .order_by(AIUsageEvent.capability, AIUsageEvent.quality_level)
        )
    ).all()
    items = []
    for row in rows:
        generations = int(row.generations or 0)
        known = int(row.known_cost_count or 0)
        cost = Decimal(row.reported_cost) if row.reported_cost is not None else None
        items.append(
            {
                "capability": row.capability,
                "quality_level": row.quality_level,
                "generations": generations,
                "total_tokens": int(row.total_tokens) if row.total_tokens is not None else None,
                "reported_cost": format(cost, "f") if cost is not None else None,
                "known_cost_count": known,
                "unknown_cost_count": generations - known,
                "currency": row.currency,
            }
        )
    payload: dict[str, object] = {"period_days": USAGE_PERIOD_DAYS, "items": items}
    # Preserve the original compact response when the cap is disabled. The
    # optional block is shown only for a configured beta budget.
    if settings.monthly_ai_budget_usd > 0:
        payload["limit"] = await usage_limit_snapshot(db, workspace_id=workspace_id)
    return payload


@router.post("/account/delete", status_code=202)
async def request_account_deletion(
    body: DeleteAccountRequest,
    response: Response,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke access now, purge later. Idempotent for the same client token."""

    job = await apply_account_deletion(
        db,
        user_id=principal.user["id"],
        confirmation=body.confirmation,
        status_token=body.status_token,
    )
    delete_session_cookie(response)
    delete_csrf_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"status": job.status}


@router.get("/account/deletion-status")
async def deletion_status(
    response: Response,
    status_token: str | None = Header(None, alias="X-Deletion-Status-Token", max_length=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public, session-less status lookup. Exposes only a coarse status."""

    response.headers["Cache-Control"] = "no-store"
    if not status_token:
        raise ForbiddenError("El token de estado no es válido.")
    return {"status": await read_public_deletion_status(db, status_token)}


@router.get("/csrf")
async def csrf_token(
    response: Response,
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    signup_token: str | None = Cookie(None, alias=SIGNUP_COOKIE),
) -> dict[str, str | None]:
    context = _pick_context("/api/v1/auth/csrf", session_token, signup_token)
    if context is None:
        response.headers["Cache-Control"] = "no-store"
        return {"token": None}
    context_token, context_name = context
    token = _generate_csrf_token(context_token, context_name)
    set_csrf_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return {"token": token}
