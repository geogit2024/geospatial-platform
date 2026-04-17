import asyncio
from html import escape

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from config import get_settings
from services.emailer import EmailDeliveryError, email_configured, send_email

router = APIRouter(prefix="/notifications", tags=["notifications"])


class InviteUserRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    inviter_name: str = Field(min_length=2, max_length=120)
    invitee_name: str = Field(min_length=2, max_length=120)
    invitee_email: str = Field(min_length=5, max_length=254)
    role: str = Field(min_length=3, max_length=32)


class AdminWelcomeRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    admin_name: str = Field(min_length=2, max_length=120)
    admin_email: str = Field(min_length=5, max_length=254)


class NotificationResponse(BaseModel):
    status: str
    message: str


def _require_email_config() -> None:
    if not email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not configured on server",
        )


def _validate_email(value: str) -> str:
    candidate = value.strip()
    if "@" not in candidate or "." not in candidate.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address",
        )
    return candidate


@router.post("/invite-user", response_model=NotificationResponse)
async def send_invite_user_email(payload: InviteUserRequest) -> NotificationResponse:
    _require_email_config()
    invitee_email = _validate_email(payload.invitee_email)

    settings = get_settings()
    login_link = f"{settings.app_public_url.rstrip('/')}/acesso"

    subject = f"Convite para acessar a plataforma GeoPublish - {payload.company_name}"
    text_body = (
        f"Ola, {payload.invitee_name}!\n\n"
        f"{payload.inviter_name} convidou voce para acessar o workspace {payload.company_name} "
        f"com perfil {payload.role}.\n\n"
        f"Acesse: {login_link}\n\n"
        "Se voce nao reconhece este convite, ignore este e-mail."
    )
    html_body = f"""
        <p>Ola, {escape(payload.invitee_name)}!</p>
        <p>
            <strong>{escape(payload.inviter_name)}</strong> convidou voce para acessar
            o workspace <strong>{escape(payload.company_name)}</strong>
            com perfil <strong>{escape(payload.role)}</strong>.
        </p>
        <p>
            <a href="{escape(login_link)}">Clique aqui para acessar a plataforma</a>
        </p>
        <p>Se voce nao reconhece este convite, ignore este e-mail.</p>
    """

    try:
        await asyncio.to_thread(
            send_email,
            to_email=invitee_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return NotificationResponse(status="sent", message="Invite email sent")


@router.post("/admin-welcome", response_model=NotificationResponse)
async def send_admin_welcome_email(payload: AdminWelcomeRequest) -> NotificationResponse:
    _require_email_config()
    admin_email = _validate_email(payload.admin_email)

    settings = get_settings()
    login_link = f"{settings.app_public_url.rstrip('/')}/acesso"

    subject = f"Bem-vindo(a) ao GeoPublish - {payload.company_name}"
    text_body = (
        f"Ola, {payload.admin_name}!\n\n"
        f"Sua empresa {payload.company_name} foi cadastrada com sucesso.\n"
        f"Acesse a plataforma: {login_link}\n\n"
        "Equipe GeoPublish"
    )
    html_body = f"""
        <p>Ola, {escape(payload.admin_name)}!</p>
        <p>Sua empresa <strong>{escape(payload.company_name)}</strong> foi cadastrada com sucesso.</p>
        <p><a href="{escape(login_link)}">Acesse a plataforma</a></p>
        <p>Equipe GeoPublish</p>
    """

    try:
        await asyncio.to_thread(
            send_email,
            to_email=admin_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return NotificationResponse(status="sent", message="Welcome email sent")
