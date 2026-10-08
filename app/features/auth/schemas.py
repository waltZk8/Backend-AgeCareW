"""
Schemas de entrada/salida del feature `auth`.

Los nombres de campo replican exactamente lo que envía/espera
`lib/features/auth/data/auth_repository.dart` y lo que documenta la sección
3.1 de la Especificación de Endpoints Backend v1.
"""
import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import RoleType


class RegisterRequest(BaseModel):
    """Body de POST /api/v1/auth/register."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    # La regla (mínimo 8, al menos una letra y un número) es la misma que ya
    # valida register_screen.dart en el cliente; se repite aquí porque el
    # backend NUNCA debe confiar en la validación del cliente.
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    # Aceptado por compatibilidad de contrato con la app, pero el flujo de
    # invitaciones es explícitamente parte de un hito posterior (módulo de
    # Pacientes/Onboarding completo, sección 4.5-4.6 de la especificación).
    # Si llega, el endpoint responde 400 FEATURE_NOT_AVAILABLE en vez de
    # ignorarlo silenciosamente (ver app/features/auth/router.py).
    invitation_token: str | None = None
    locale: str = Field(default="es", max_length=8)

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: str) -> str:
        if not re.search(r"[a-zA-Z]", v) or not re.search(r"[0-9]", v):
            raise ValueError("Debe incluir al menos una letra y un número")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Escribe tu nombre completo")
        return v


class RegisterResponse(BaseModel):
    """
    Respuesta 201 de POST /api/v1/auth/register.

    `role` viaja siempre en `null` en este MVP porque el flujo de invitación
    (único caso en que el registro trae un rol asignado) no está implementado
    todavía. `auth_repository.dart` ya maneja ese caso: si `role` es null,
    usa la sesión recién creada tal cual, sin llamar a GET /users/me.
    """

    user_id: UUID
    email: EmailStr
    role: RoleType | None = None
    access_token: str
    refresh_token: str


class LoginRequest(BaseModel):
    """Credenciales de POST /api/v1/auth/login."""

    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(RegisterResponse):
    """Mismo contrato de sesión que el registro; role sigue siendo contextual."""
