"""
Lógica de negocio del feature `auth`, separada del router HTTP para que el
endpoint (app/features/auth/router.py) quede como una capa delgada de
entrada/salida.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.features.auth.schemas import LoginRequest, RegisterRequest
from app.models.user import User


# Mantiene un costo de verificación comparable cuando el correo no existe.
# Nunca representa una cuenta válida y no contiene credenciales de usuario.
_DUMMY_PASSWORD_HASH = hash_password("agecare-nonexistent-account")


async def login_user(db: AsyncSession, data: LoginRequest) -> tuple[User, str, str]:
    """Valida credenciales y emite una sesión sin revelar si el correo existe."""
    user = await db.scalar(select(User).where(User.email == data.email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(data.password, password_hash)

    if user is None or not password_valid:
        raise AppError(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Correo o contraseña incorrectos.",
        )

    return user, create_access_token(user.id), create_refresh_token(user.id)


async def register_user(db: AsyncSession, data: RegisterRequest) -> tuple[User, str, str]:
    """
    Crea la cuenta de un usuario familiar y devuelve (usuario, access_token,
    refresh_token).

    Errores (además de los comunes de la sección 2.5):
      * 409 EMAIL_ALREADY_EXISTS -- ya existe una cuenta con ese correo.
      * 400 FEATURE_NOT_AVAILABLE -- se envió invitation_token (ver nota
        de alcance más abajo).
    """
    if data.invitation_token is not None:
        # El registro vía invitación (cuidadora/médico/adulto mayor que se
        # suman a un círculo de cuidado ya existente) depende de los
        # endpoints 4.5/4.6 (invitaciones), que pertenecen al módulo de
        # Pacientes/Onboarding completo y no a este primer hito. Se rechaza
        # explícitamente en vez de ignorar el campo y crear una cuenta sin
        # la membresía que el usuario esperaba.
        raise AppError(
            status_code=400,
            code="FEATURE_NOT_AVAILABLE",
            message=(
                "El registro mediante invitación aún no está disponible. "
                "Crea tu cuenta sin invitación por ahora."
            ),
        )

    # Verificación previa "amigable": evita el costo de una excepción SQL en
    # el camino feliz. La UNIQUE constraint de la tabla (ver User.email)
    # sigue siendo la garantía real ante condiciones de carrera; por eso el
    # bloque try/except de abajo también existe.
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        raise AppError(
            status_code=409,
            code="EMAIL_ALREADY_EXISTS",
            message="Ya existe una cuenta con este correo electrónico.",
        )

    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        phone=data.phone,
        locale=data.locale,
    )
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        # Dos registros concurrentes con el mismo correo: el SELECT de
        # arriba no lo detectó porque llegaron casi al mismo tiempo, pero la
        # UNIQUE constraint de PostgreSQL sí. Se traduce al mismo error de
        # negocio en vez de dejar pasar el 500 genérico de IntegrityError.
        await db.rollback()
        raise AppError(
            status_code=409,
            code="EMAIL_ALREADY_EXISTS",
            message="Ya existe una cuenta con este correo electrónico.",
        ) from None

    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return user, access_token, refresh_token
