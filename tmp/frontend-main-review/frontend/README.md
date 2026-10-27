# VoxReady — Client

Frontend web de **VoxReady**, plataforma SaaS de entrenamiento en vocería de crisis y evaluación multimodal con inteligencia artificial (voz, imagen y contenido).

Desarrollado con **Next.js 16 (App Router)**, **React 19** y **TypeScript**.

---

## Características Principales

- **Arquitectura basada en Roles:**
  - **Vocero (`/spokesperson`):** Práctica en tiempo real, catálogo de escenarios de crisis, consentimiento informado, teleprompter/simulador interactivo, análisis en tiempo real y reporte tipo coach.
  - **Administrador de Cliente (`/admin`):** Métricas del tenant corporativo, configuración de temas institucionales, mensajes clave, líneas rojas y políticas de retención de grabaciones.
  - **Configurador Maestro (`/master`):** Estándar global de rúbricas multimodales, ponderación por canales (expresión, voz, coherencia, empatía) y cola de etiquetado/calibración con expertos humanos.
- **Enrutamiento por App Router:** Subrutas limpias (`/login`, `/spokesperson`, `/admin`, `/master`) organizadas mediante route groups.
- **Soporte Multilingüe (i18n):** Traducción integrada en Español, Inglés y Portugués (`src/locales/` + `I18nContext`).
- **Capa de Servicios HTTP (`src/services/`):** Integración estandarizada con la API REST del backend (`apiClient`), soporte de errores RFC 7807 (Problem Details), trazabilidad mediante `x-correlation-id` y modo de contingencia con datos mock (`src/mock/mockData.ts`).

---

## Requisitos

- Node.js 20.x o superior
- npm 10.x o superior

---

## Instalación y Ejecución Local

```bash
# 1. Instalar dependencias
npm install

# 2. Iniciar servidor de desarrollo
npm run dev

# 3. Compilar para producción
npm run build

# 4. Iniciar servidor de producción
npm run start
```

La aplicación estará disponible en [http://localhost:3000](http://localhost:3000).

---

## Variables de Entorno

Puedes configurar un archivo `.env.local`:

```env
# URL de la API del Backend (FastAPI)
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

Si el backend no está disponible en esa URL, el cliente continuará funcionando de forma autónoma con datos simulados gracias a los fallbacks de `src/services/`.

---

## Estructura del Código

```text
src/
├── app/                  # Next.js App Router (rutas /login, /spokesperson, /admin, /master)
├── components/
│   ├── auth/             # Vistas de autenticación
│   ├── client-admin/     # Vistas para el administrador corporativo
│   ├── common/           # Cabeceras, barras laterales y controles globales
│   ├── master/           # Vistas para el configurador maestro de la plataforma
│   └── spokesperson/     # Flujo completo del vocero (práctica, consentimiento, simulador, reporte)
├── context/              # Contextos de React (AuthContext, I18nContext, ThemeContext)
├── locales/              # Diccionarios de traducción (es.ts, en.ts, pt.ts)
├── mock/                 # Datos semilla y mocks para pruebas sin backend
├── services/             # Clientes de API REST (apiClient, sessionService, topicService, rubricService)
└── types/                # Definiciones e interfaces de TypeScript
```
