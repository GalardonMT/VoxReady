# Barras de navegación por rol

## Fase 1: preparación completada

- Fecha: 24 de noviembre de 2026.
- Rama: `feat/barra-navegacion-roles`.
- Base: `origin/main`, actualizada mediante `git fetch origin main`.
- Commit base: `d03f7da47512c22c4d825ee7a2912ab26c6fba33` (merge de PR #19).
- Árbol de trabajo limpio antes de crear la rama y después de las comprobaciones.
- Esta fase registra la base y el alcance; la implementación visual comienza en la fase 2.

## Diseño acordado

Conservar el logo real y la paleta de VoxReady. Usar iconos ilustrativos consistentes,
selección con borde azul y fondo tenue, navegación centrada y separación uniforme.
El usuario y el botón «Cerrar sesión» se ubican a la derecha.
Las imágenes aprobadas son referencias visuales; el logo del proyecto es la fuente final.

| Rol | Navegación acordada | Identificación junto al logo |
| --- | --- | --- |
| Configurador maestro | Panel Maestro · Evaluación ▾ · Contenidos ▾ · Clientes | Configurador maestro |
| Cliente | Panel del Cliente · Voceros · Escenarios · Actividad | Nombre del cliente, con alternativa «Cliente» |
| Vocero | Inicio · Catálogo · Mi Progreso · Microlecciones | Solo el logo |

| Menú de maestro | Pantalla existente | Descripción propuesta |
| --- | --- | --- |
| Evaluación: Editor de Rúbrica | `m2` | Define criterios de evaluación |
| Evaluación: Editor de métricas | `m7` | Configura indicadores y pesos |
| Evaluación: Cola de Etiquetado | `m3` | Revisa casos pendientes |
| Contenidos: Catálogo de temas | `m4` | Explora temas y escenarios |
| Contenidos: Editor de temas y escenarios | `m5` | Crea y ajusta contenidos |
| Contenidos: Microlecciones | `m6` | Gestiona contenidos de aprendizaje |

Panel Maestro conserva `m1` y Clientes conserva `m8`.
Cada opción del desplegable tendrá icono a la izquierda, título y descripción corta.

## Inspección de la base

| Fuente | Hallazgo y consideración para implementar |
| --- | --- |
| `frontend/src/app/(master)/master/page.tsx` | Ocho opciones planas; navegación por estado. La cola respeta `NEXT_PUBLIC_LABELING_UI_ENABLED`. El editor de métricas permanece montado después de la primera visita. El editor de temas conserva la selección. |
| `frontend/src/components/client-admin/ClientAdminHeader.tsx` | Cuatro opciones; nombre del cliente y cierre de sesión. Se usa también desde el detalle del vocero del cliente. |
| `frontend/src/app/(spokesperson)/spokesperson/page.tsx` | Cuatro opciones. `handleHeaderNavigate` y `handleHeaderLogout` solicitan confirmación durante una práctica activa; deben seguir siendo los puntos de entrada. |
| `frontend/src/app/globals.css` | `.vocero-nav-tabs` tiene `margin-left: auto` y `overflow-x: auto`; se oculta por debajo de 900 px. Las tres barras comparten clases. |
| `frontend/tests/clientAdminCleanup.test.mjs` y `clientAdminScope.test.mjs` | Algunas aserciones buscan literalmente «Escenarios disponibles» y «Actividad y uso». Actualizarlas junto con los textos en fase 3, conservando las comprobaciones de alcance del rol. |

Stack declarado: Next.js 16.4.6, React 19.2.8 y TypeScript.
`lucide-react` ya está disponible para los iconos. El frontend exporta páginas estáticas.
Entorno de comprobación: Node.js 24.13.0 y npm 11.6.2.

## Criterios técnicos

- Reutilizar una estructura de cabecera para la disposición y estilos comunes; mantener las decisiones de navegación y de sesión en cada rol.
- Usar estilos acotados al nuevo componente, evitando que el contenedor con desplazamiento recorte los desplegables.
- Conservar las variables de color existentes y los identificadores de pantalla.
- Implementar los desplegables como controles de expansión: apertura por mouse y clic, `aria-expanded`, foco visible, acceso por Tab y cierre con Escape, al seleccionar una opción y al salir del menú. El menú debe permitir mover el puntero desde su botón hacia las opciones.
- Resaltar el grupo que contiene la pantalla activa y distinguir la opción seleccionada.
- Centrar el grupo respecto de la cabecera cuando haya espacio. En anchos pequeños, adaptar la distribución sin solapar marca, navegación y usuario, con acceso a todas las secciones.
- Evitar nuevas dependencias para estos controles; respetar la preferencia de movimiento reducido.

Se consultó Context7 para Next.js 16.4.5, la versión documentada más cercana disponible,
y la documentación instalada de Next.js 16.4.6 según `frontend/AGENTS.md`:
`01-app/03-api-reference/01-directives/use-client.md` y
`01-app/01-getting-started/05-server-and-client-components.md`.
La interacción se mantiene en componentes cliente; los estilos pueden encapsularse en CSS Modules.
Referencias: [use client](https://nextjs.org/docs/app/api-reference/directives/use-client)
y [CSS Modules](https://nextjs.org/docs/app/getting-started/css#css-modules).
Para el flujo de rama y commits se aplicó la guía `ecc:git-workflow`.

## Comprobaciones de la base

Ejecutadas desde `frontend/`, antes de cambiar el código de la aplicación:

| Comprobación | Resultado |
| --- | --- |
| `npm run build` | Correcta: compilación, TypeScript y exportación de páginas estáticas. |
| `npm run test:routes` | 2 pruebas correctas. |
| `npm run test:client-admin` | 10 pruebas correctas. |
| `npm run test:client-scenarios` | 4 pruebas correctas. |
| `npm run test:labeling` | 16 pruebas correctas. |
| `npm run lint` | Falla preexistente: 36 errores y 12 advertencias. |

Los errores de lint incluyen reglas de hooks en `AnalyzingView`, `InterviewerAvatar`,
`LiveSessionView` y `AuthContext`, tipos `any` en servicios y `CoachReportView`,
y una variable `module` en `clientSpokespersonsView.test.mjs`.
Las pruebas emiten advertencias de Node sobre módulos sin tipo declarado.
No se modificaron dependencias ni configuración para ocultar estos resultados.
La inspección de esta fase fue de código y de las capturas aportadas; todavía no se ha
realizado una comprobación visual de la aplicación en navegador.

## Fase 2: maestro completado

- `PlatformHeader` aporta la estructura común de marca, navegación centrada y usuario, con estilos encapsulados en CSS Modules y el logo real mediante `next/image`.
- `MasterNavigation` organiza Evaluación y Contenidos con iconos de Lucide, títulos y descripciones; Panel Maestro y Clientes conservan sus accesos directos.
- El distintivo muestra «Configurador maestro». El maestro ya usa «Cerrar sesión»; cliente y vocero adoptarán esta cabecera en fase 3.
- Un solo desplegable puede estar abierto. Admite hover de mouse, clic, Tab y Escape, y se cierra al seleccionar, abandonar el foco o pulsar fuera. Escape y la selección devuelven el foco al botón del grupo.
- La opción y el grupo activos se distinguen por separado. La cola sigue dependiendo de `NEXT_PUBLIC_LABELING_UI_ENABLED`.
- La cabecera se distribuye en dos filas cuando falta espacio; a 600 px o menos las cuatro opciones se presentan en dos columnas. La navegación del maestro ya no desaparece por la regla global de 900 px.
- El contenido de las pantallas y sus manejadores de navegación conservan su estructura, incluido el estado de selección del editor de temas.

Comprobaciones realizadas:

| Comprobación | Resultado |
| --- | --- |
| `npm run build` | Correcta: compilación, TypeScript y exportación estática. |
| ESLint en la página del maestro, los dos componentes nuevos y `masterNavigation.test.mjs` | Correcto, sin errores ni advertencias. |
| Pruebas de rutas, modelos y vista del panel maestro y los cuatro modelos de etiquetado | 24 pruebas correctas. |
| `node --experimental-strip-types --test tests/masterNavigation.test.mjs` | 3 pruebas correctas: cola condicional, pantalla/grupo activos y semántica inicial de los desplegables. |
| Edge local, compilación exportada, sesión simulada | Correctos: hover, paso del puntero al panel, centrado, Tab, Escape con devolución de foco, clic, selección y cierre exterior. |
| Editor de métricas en Edge | La misma instancia DOM permanece montada al salir y se reutiliza al volver. |
| Capturas en Edge a 1600 × 900 y 375 × 812 | Revisadas; navegación y desplegables visibles, sin desbordamiento horizontal a 375 px. |

ECC no pudo iniciar Chrome porque no está instalado; la revisión visual se hizo con Edge
en un perfil temporal. Las respuestas de autenticación se simularon en el navegador y las
peticiones de datos de la API se bloquearon para esta comprobación. Esto verifica la interfaz
y la conservación del montaje del editor, pero no valida cargas o guardados contra la API real.
No se repitió el lint general: sus fallos base siguen documentados en fase 1.
Se aplicó `ecc:frontend-patterns` y se volvió a consultar Context7 para componentes cliente,
CSS Modules y dimensiones de `next/image`, junto a la documentación instalada de Next.js.

## Fase 3: cliente y vocero completados

- Cliente y vocero adoptan `PlatformHeader`, con marca a la izquierda, navegación centrada y usuario y «Cerrar sesión» a la derecha.
- `SectionNavigation` presenta cuatro botones con iconos de Lucide, separación uniforme y `aria-current` para la sección activa. A 600 px o menos usa dos columnas, con las cuatro secciones accesibles.
- Cliente conserva el nombre de la organización o «Cliente» como alternativa y el avatar naranja. Los accesos se llaman Panel del Cliente, Voceros, Escenarios y Actividad.
- Vocero conserva solo el logo a la izquierda. Sus accesos son Inicio, Catálogo, Mi Progreso y Microlecciones.
- La cabecera reutilizada en el detalle de voceros del cliente mantiene Voceros activo y respeta los retornos a las secciones de `/admin`.
- Las acciones de cabecera del vocero continúan pasando por `handleHeaderNavigate` y `handleHeaderLogout`. Durante `u4`, cambiar de sección, pulsar el logo o cerrar sesión solicita confirmación.
- Se actualizaron las aserciones de cliente que dependían de los textos anteriores; se conservaron las comprobaciones de alcance del rol.

Comprobaciones realizadas:

| Comprobación | Resultado |
| --- | --- |
| `npm run build` | Correcta: compilación, TypeScript y exportación estática. |
| ESLint de los componentes TSX y las pruebas modificadas o nuevas de esta fase | Correcto, sin errores ni advertencias. |
| Rutas, alcance del cliente, escenarios de cliente, navegación del maestro y reglas/presentación de microlecciones | 28 pruebas correctas. |
| `node --experimental-strip-types --test tests/spokespersonHeaderNavigation.test.mjs` | 4 pruebas correctas: interceptar las salidas durante una práctica, continuarla, confirmar su cancelación y navegar/cerrar sesión fuera de una práctica. |
| Edge local con respuestas simuladas | Cuatro opciones y selección correctas en ambos roles; navegación centrada a 1600 px; cierre de sesión hacia login; detalle de vocero con Voceros activo y retorno a Escenarios. |
| Capturas a 1600 × 900 y 375 × 900, cliente y vocero | Revisadas; botones de navegación visibles y dentro del ancho disponible. |

La revisión en Edge empleó un perfil temporal y autenticación simulada; las peticiones de
datos de la API se bloquearon. Las pruebas de protección durante una práctica invocan los
manejadores reales de la página con estado controlado, sin montar captura de medios ni
conectarse al backend. La grabación y la autenticación real no se validaron en esta fase.
Se siguió la composición de componentes de `ecc:frontend-patterns`, la documentación
instalada de Next.js y la consulta de Context7 sobre componentes cliente y CSS Modules.

## Fase 4: revisión final completada

Se corrigieron tres problemas encontrados durante la revisión:

- El menú abierto con hover ahora se cierra con Escape aunque el foco esté fuera de la navegación. Si el foco está dentro, vuelve al botón del grupo; si está fuera, conserva su ubicación. Una prueba de regresión comprueba ambos casos y la limpieza de los listeners.
- El bloque de usuario respeta el ancho de su columna. Los nombres largos se abrevian visualmente con puntos suspensivos y conservan el texto completo en `title`, sin invadir la navegación ni ocultar «Cerrar sesión».
- Los textos secundarios usan un color derivado de la paleta con mayor contraste. En tema oscuro, se aclaran los acentos de selección, iconos y foco dentro de la cabecera. Los ajustes están encapsulados y conservan las variables de color generales.

| Comprobación final | Resultado |
| --- | --- |
| `npm run build` | Correcta, incluida la comprobación de TypeScript y la exportación estática. El primer intento encontró un error EPERM al crear una carpeta de `.next`; la repetición con permisos de ejecución ampliados terminó correctamente. |
| `node --experimental-strip-types --test tests/*.test.mjs` | 75 pruebas aprobadas, sin fallos. |
| ESLint sobre todos los archivos TSX/MJS modificados respecto de la base | 0 errores y 0 advertencias en 10 archivos. |
| ESLint general, mediante su API sobre el frontend | 36 errores y 9 advertencias. Los errores permanecen en los archivos preexistentes enumerados en fase 1; se eliminaron las tres advertencias de imágenes de las cabeceras. |
| Matriz local en Edge | 61 comprobaciones correctas, sin incidencias pendientes en esa matriz. |
| Regresión de las comprobaciones de fases 2 y 3 | Correctas tras los ajustes: hover y paso al panel, selección, foco, cierre exterior, montaje persistente de métricas, navegación de cliente/vocero, cierre de sesión y retorno desde el detalle de vocero. |

La matriz de Edge cubrió los tres roles con nombres de usuario largos, y un nombre de
organización largo insertado como dato de prueba de presentación. Se comprobaron estos
anchos: 320, 375, 600, 601, 768, 900, 1024, 1200, 1201, 1280, 1366, 1600 y 1920 px.
En todos ellos los bloques de la cabecera quedaron sin solapamientos y los botones visibles
dentro de la pantalla, con al menos 24 × 24 px. El ancho de 320 px también comprueba la
redistribución necesaria al reducir un escritorio de 1280 px a una cuarta parte.

Con la paleta VoxReady se midió contraste de al menos 4,5:1 para el texto de la sección
activa y el subtítulo de usuario en los temas claro y oscuro. Se verificaron foco visible,
movimiento reducido, Enter y Espacio para abrir, Tab para entrar y salir, Escape y su
conservación/devolución de foco. La emulación táctil abrió Contenidos y seleccionó
Microlecciones a 320 px. Las capturas finales de los tres roles a 1600 px y del menú táctil
a 320 px se revisaron visualmente.

La revisión utilizó una compilación local y un perfil temporal de Edge, con autenticación
simulada y peticiones de datos de la API bloqueadas. La entrada táctil fue emulada; no se
probó un dispositivo físico ni un lector de pantalla. La autenticación real, la captura de
medios y los guardados contra la API no forman parte de estos resultados. Los datos del
contenido de las capturas corresponden a estados vacíos, errores o valores ya existentes
en la aplicación; no son evidencia de resultados de usuarios reales.

Se aplicó `ecc:accessibility` para esta revisión y se consultaron Context7 y la documentación
instalada de Next.js. Las cuatro fases acordadas quedan completadas en la rama local
`feat/barra-navegacion-roles`.

## Seguimiento de fases y commits

1. **Fase 2 — Maestro, completada:** estructura compartida y desplegables de Evaluación y Contenidos, iconos y descripciones y nuevo distintivo. Commit: `feat(nav): agrupar la navegacion del maestro`.
2. **Fase 3 — Cliente y vocero, completada:** cabecera y navegación comunes, cuatro opciones centradas y textos aprobados. Verificados el detalle de voceros y la protección de prácticas activas. Commit: `feat(nav): unificar las barras de cliente y vocero`.
3. **Fase 4 — Verificación, completada:** corregidos Escape para hover, solapamientos con nombres largos y contraste local. Compilación, pruebas, lint del cambio y matriz de navegador verificados. Commit: `fix(nav): completar ajustes de accesibilidad y adaptacion`.

Una sola rama y un commit por fase. Las cuatro fases están completadas.
