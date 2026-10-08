# AgeCare — Backend (Hito 1 / MVP)

API REST de AgeCare construida con **FastAPI + SQLAlchemy 2 (async) + PostgreSQL + Alembic**,
implementando el primer hito: fundaciones del proyecto, conexión a base de datos, y los
módulos core `auth` y `patients`.

Todo el código de este entregable fue **efectivamente instalado, migrado contra un
PostgreSQL real y probado end-to-end** (registro, creación de paciente, membresías,
errores 401/403/404/409/422/429) antes de entregarse — no es solo código de referencia.

**Incremento posterior:** se añadió `POST /api/v1/auth/login` con pruebas HTTP
usando una sesión de base de datos simulada. Ese endpoint aún no se ha probado
contra PostgreSQL real en este incremento. La demo web de `AgeCare-Frontend-v1W/demo-web`
utiliza acceso ficticio local y no consulta esta API.

## 1. Por qué esta estructura de carpetas

El frontend Flutter organiza `lib/` en `core/` (infraestructura transversal: red, storage,
config) y `features/<dominio>/` (un paquete por dominio de negocio: `auth`, `patients`,
`health`, `medications`, etc.). Este backend replica exactamente esa filosofía:

```
app/
├── core/                    # infraestructura transversal (equivalente a lib/core/)
│   ├── config.py            # Settings (variables de entorno)
│   ├── database.py          # engine async, sessionmaker, Base declarativa, get_db
│   ├── security.py          # hash de contraseñas (Argon2) + JWT
│   ├── middleware.py        # request_id para trazabilidad
│   ├── exceptions.py        # AppError + manejadores globales de error
│   └── rate_limit.py        # limitador simple (ver limitaciones más abajo)
│
├── models/                  # modelos SQLAlchemy (compartidos entre features)
│   ├── enums.py              # RoleType, SexType (mismos valores que la API/frontend)
│   ├── mixins.py             # TimestampMixin (created_at/updated_at)
│   ├── user.py                # tabla `users`
│   ├── patient.py             # tabla `patients`
│   └── patient_member.py      # tabla `patient_members` (autorización por recurso)
│
├── features/                # un paquete por dominio, igual que lib/features/
│   ├── auth/
│   │   ├── schemas.py        # Pydantic: RegisterRequest / RegisterResponse
│   │   ├── service.py         # lógica de negocio (crear usuario, hashear, emitir JWT)
│   │   └── router.py          # POST /auth/register, POST /auth/login
│   └── patients/
│       ├── schemas.py
│       ├── service.py
│       └── router.py          # POST /patients, GET /patients/{id}
│
├── api/
│   ├── deps.py                # get_current_user (valida Bearer token)
│   └── router.py               # agrega los routers de cada feature bajo /api/v1
│
└── main.py                     # arma la app, middleware, manejador de errores, healthcheck
```

Los próximos módulos (`health`/vitals, `medications`, `alerts`, `comms`, `elder`,
`caregiver`, `marketplace`, `documents`, `premium`, `wearable`) se agregan cada uno como
`app/features/<mismo_nombre_que_en_flutter>/`, con la misma forma interna
(`schemas.py` + `service.py` + `router.py`), y se registran en `app/api/router.py`.

## 2. Requisitos previos

- Python 3.12
- Docker + Docker Compose (recomendado) **o** un PostgreSQL 16 accesible localmente
- (Opcional) `psql` si quieres inspeccionar la base de datos a mano

## 3. Levantar la base de datos

### Opción A — Docker (recomendada)

```bash
docker compose up -d
```

Esto levanta un PostgreSQL 16 en `localhost:5432` con usuario/clave/base de datos
`agecare` / `agecare` / `agecare`, con los datos persistidos en un volumen Docker.

### Opción B — PostgreSQL instalado localmente

Crea el rol y la base de datos manualmente:

```sql
CREATE ROLE agecare WITH LOGIN PASSWORD 'agecare';
CREATE DATABASE agecare OWNER agecare;
```

## 4. Configurar el entorno de Python

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env si tu base de datos no usa los valores por defecto.
```

## 5. Ejecutar las migraciones

**Importante:** invoca Alembic como módulo (`python -m alembic`, no solo `alembic`) para
que Python encuentre el paquete `app/` al ejecutarse desde la raíz del proyecto.

```bash
python -m alembic upgrade head
```

Esto crea las tablas `users`, `patients`, `patient_members` y los tipos ENUM nativos
(`sex_type`, `role_type`) en PostgreSQL. Para generar una migración nueva más adelante
(cuando se agreguen más modelos):

```bash
python -m alembic revision --autogenerate -m "descripción del cambio"
python -m alembic upgrade head
```

## 6. Levantar el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

- Documentación interactiva (Swagger): http://localhost:8000/docs
- Healthcheck: http://localhost:8000/health y http://localhost:8000/api/v1/health

## 7. Probar los endpoints

### Registrar un familiar

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
        "full_name": "Carlos Pérez",
        "email": "carlos@example.com",
        "password": "clave1234",
        "phone": "+56912345678"
      }'
```

Respuesta (201):

```json
{
  "user_id": "0b461bf2-...",
  "email": "carlos@example.com",
  "role": null,
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

### Iniciar sesión con una cuenta registrada

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"carlos@example.com","password":"clave1234"}'
```

Devuelve `user_id`, `email`, `role: null`, `access_token` y `refresh_token`,
con el mismo contrato del registro. Una contraseña o un correo incorrecto
devuelve `401 INVALID_CREDENTIALS` sin indicar cuál de los dos falló. El rol
continúa siendo contextual a una membresía de paciente, no a la cuenta.

### Crear un paciente (requiere el access_token de arriba)

```bash
curl -X POST http://localhost:8000/api/v1/patients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -d '{
        "full_name": "Elena Pérez",
        "birth_date": "1948-03-02",
        "sex": "female",
        "conditions": ["Hipertensión", "Artrosis"],
        "notes": "Le gusta el jardín"
      }'
```

Quien hace esta petición queda automáticamente como familiar administrador (`is_owner=true`,
`role=family`) del paciente en `patient_members`.

### Ver el detalle del paciente

```bash
curl http://localhost:8000/api/v1/patients/<PATIENT_ID> \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Un usuario que no pertenece al círculo de cuidado del paciente recibe `403 FORBIDDEN`; un
`patient_id` inexistente recibe `404 NOT_FOUND`.

### Formato de error

Cualquier error de la API responde siempre con esta forma (probado para 401, 403, 404,
409, 422 y 429):

```json
{
  "error": {
    "code": "EMAIL_ALREADY_EXISTS",
    "message": "Ya existe una cuenta con este correo electrónico.",
    "details": null,
    "request_id": "802b82ec-bdd5-44ac-bee3-b30c1b40a9c9"
  }
}
```

`details` viene poblado (lista de `{field, message}`) específicamente en errores 422 de
validación.

## 8. Alcance de este hito y próximos pasos

Este entregable implementó **exactamente** lo pedido: modelos de Usuarios/Pacientes/
Membresías, migraciones de Alembic, `POST /auth/register`, `POST /patients` y el manejador
global de errores. Además se agregó `GET /patients/{id}`, no pedido explícitamente, porque
`create_patient_screen.dart` lo invoca inmediatamente después de crear el paciente
(`PatientsRepositoryHttp.createPatient` hace `POST /patients` y después `GET
/patients/{id}`) — sin él, esa pantalla fallaría justo después de un `201` exitoso.

Quedan **fuera de alcance**, y son los siguientes pasos naturales según el Plan de
Desarrollo (equivalen a los tickets AGE-104 y AGE-201/202 de Sprint 1-2):

- `POST /auth/refresh`, `POST /auth/logout` y recuperación de contraseña.
  Refresh/logout seguros requieren la tabla `refresh_tokens` para rotación y
  revocación del lado del servidor. No se presentan como implementados.
- Endpoints de invitaciones (`POST /patients/{id}/invitations`, `POST
  /invitations/accept`): por eso `POST /auth/register` responde `400
  FEATURE_NOT_AVAILABLE` si se envía `invitation_token` — se rechaza explícitamente en
  vez de ignorarlo y crear una cuenta sin la membresía que el usuario esperaba.
- `GET /patients` (listado multi-paciente), `PATCH /patients/{id}`.
- Registro de dispositivos push (`POST /users/me/devices`) y vinculación de wearable.

### Limitaciones conocidas a tener en cuenta

- **Rate limiting (`app/core/rate_limit.py`)**: es un limitador en memoria, por proceso,
  aplicado a registro y login como demostración de que el formato 429 funciona.
  No sirve con más de una instancia del backend corriendo (cada una tendría su propio
  contador) ni sobrevive un reinicio. Para producción, usar Azure API Management o un
  limitador respaldado por Redis (`slowapi`, `fastapi-limiter`).
- **Refresh token sin persistencia**: `POST /auth/register` ya emite `access_token` y
  `refresh_token` (JWT autocontenidos) para que el flujo de `auth_controller.dart` funcione
  hoy, pero el refresh token todavía no se puede revocar del lado del servidor porque la
  tabla `refresh_tokens` no es parte de este hito.
- **JWT con HS256** y secreto único (`JWT_SECRET`): suficiente para este MVP; en
  producción, ese secreto debe salir de Azure Key Vault, nunca de un valor por defecto.

## 9. Despliegue en Azure (referencia)

Este proyecto no incluye IaC de Azure (fuera de alcance de este hito), pero está pensado
para desplegarse tal como describe la Guía de Instalación y Despliegue del proyecto:
Azure Database for PostgreSQL (Flexible Server) + Azure Container Apps / App Service,
con `DATABASE_URL` y `JWT_SECRET` inyectados como secretos desde Azure Key Vault, y
`python -m alembic upgrade head` corriendo como paso de release antes de iniciar
`uvicorn`/`gunicorn`.
