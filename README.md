# VoxReady — Plataforma de Entrenamiento en Vocería de Crisis

**VoxReady** es una plataforma SaaS multi-tenant diseñada para el entrenamiento de voceros organizacionales ante situaciones de crisis, incorporando evaluación multimodal asistida por IA (análisis de voz/prosodia, expresión no verbal y coherencia del mensaje institucional).

Este repositorio está organizado como un **Monorepo** que aloja tanto la API REST (Backend) como la aplicación web interactiva (Frontend).

---

## Estructura del Monorepo

```text
VoxReady/
├── .gitignore                   # Reglas globales de exclusión (entornos, caches, builds)
├── docker-compose.yml           # Orquestación de Base de Datos, Backend y Frontend
├── README.md                    # Este documento
│
├── backend/                     # API REST (FastAPI + SQLAlchemy async + PostgreSQL 16)
│   ├── .gitignore
│   ├── .env.example
│   ├── Dockerfile
│   ├── pytest.ini               # Configuración de pruebas (pythonpath = .)
│   ├── requirements.txt
│   ├── alembic/                 # Migraciones de base de datos asíncronas
│   ├── app/                     # Código fuente de la API (routers, modelos, esquemas, servicios)
│   └── tests/                   # Suite de pruebas unitarias y de integración (pytest)
│
└── frontend/             # Aplicación Web (Next.js 16 App Router + React 19 + TypeScript)
    ├── .gitignore
    ├── Dockerfile
    ├── README.md                # Documentación detallada del cliente
    ├── package.json
    ├── public/                  # Assets estáticos y logos
    └── src/
        ├── app/                 # Rutas de la aplicación (/login, /spokesperson, /admin, /master)
        ├── components/          # Componentes organizados por dominio de usuario
        ├── context/             # Proveedores de estado global (Auth, I18n, Theme)
        ├── locales/             # Soporte multidioma (ES, EN, PT)
        ├── mock/                # Datos semilla para desarrollo y fallback
        ├── services/            # Clientes HTTP hacia la API REST
        └── types/               # Definiciones de tipos TypeScript
```

---

## Requisitos Previos

- **Docker y Docker Compose** (Recomendado para levantar el entorno completo con un comando).
- O alternativamente para ejecución nativa:
  - **Python 3.12+**
  - **Node.js 20+** y **npm 10+**

---

## Arranque Rápido con Docker Compose

Para probar el flujo local con autenticación demo, PostgreSQL aislado y puertos
3100/8100, sigue [LOCAL_DOCKER.md](LOCAL_DOCKER.md). Usa el proyecto
`voxready-local` indicado allí para conservar separados los contenedores y datos
del despliegue Azure.

Para usar el inicio de sesión de Microsoft y la base Azure SQL configurados en el `.env` de la raíz, ejecuta `docker compose -f docker-compose.azure.yml up --build`. Este arranque usa el usuario vocero ya provisionado y no carga usuarios demo. Consulta [AUTENTICACION.md](AUTENTICACION.md) para los requisitos de Azure, sesión y permisos.

Para iniciar el entorno demo aislado:

```bash
docker compose -p voxready-local -f docker-compose.local.yml up --build -d --wait
```

Una vez iniciados los servicios:
- **Frontend (Aplicación Web):** [http://localhost:3100/login](http://localhost:3100/login)
- **Backend (API REST Docs):** [http://localhost:8100/docs](http://localhost:8100/docs)
- **Base de datos PostgreSQL:** dentro de la red Docker del proyecto local.

---

## Ejecución Local para Desarrollo (Sin Docker)

### 1. Backend (FastAPI + SQLite)

```bash
cd backend

# Crear y activar entorno virtual
python -m venv .venv
# En Windows:
.venv\Scripts\activate
# En Linux/Mac:
# source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env

# Aplicar migraciones y cargar datos semilla
alembic upgrade head
python -m app.seed

# Iniciar servidor de desarrollo
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (Next.js 16)

En otra terminal:

```bash
cd frontend

# Instalar dependencias
npm install

# Iniciar servidor de desarrollo
npm run dev
```

La interfaz estará disponible en [http://localhost:3000](http://localhost:3000).

---

## Perfiles de Acceso (Modo Demo)

La plataforma incluye 3 roles de usuario preconfigurados con datos semilla:

| Rol | Usuario | Email de prueba | Espacio / Ruta |
| :--- | :--- | :--- | :--- |
| **Vocero** | Ana Torres | `ana@visum.com` o `vocero@demo.voxready.io` | [`/spokesperson`](http://localhost:3000/spokesperson) |
| **Admin de Cliente** | Carlos Ruiz | `carlos@visum.com` o `admin@demo.voxready.io` | [`/admin`](http://localhost:3000/admin) |
| **Configurador Maestro** | Marta Vidal | `marta@voxready.io` o `master@voxready.io` | [`/master`](http://localhost:3000/master) |

---

## Ejecución de Pruebas

### Backend
```bash
cd backend
pytest -v
```

### Frontend
```bash
cd frontend
npm run build
npm run lint
```

La configuración de sesiones, JWT, acceso local y proveedor externo está en [AUTENTICACION.md](AUTENTICACION.md).
