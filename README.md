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
└── voxready-client/             # Aplicación Web (Next.js 16 App Router + React 19 + TypeScript)
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

La forma más rápida de levantar toda la plataforma (Base de datos PostgreSQL, Backend FastAPI y Frontend Next.js):

```bash
# 1. Clonar el repositorio y situarse en la raíz
cd VoxReady

# 2. Levantar todos los servicios en contenedores
docker compose up --build
```

Una vez iniciados los servicios:
- **Frontend (Aplicación Web):** [http://localhost:3000](http://localhost:3000)
- **Backend (API REST Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Base de datos PostgreSQL:** `localhost:5432`

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
cd voxready-client

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
cd voxready-client
npm run build
npm run lint
```
