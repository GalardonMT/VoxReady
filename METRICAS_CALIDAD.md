# Métricas de Calidad de Software

| Métrica | Valor Obtenido | Objetivo | Estado |
| :--- | :---: | :---: | :---: |
| **Velocidad de desarrollo** | **44.5 Story Points / sprint** *(Semanal)* <br> *(89.0 SP en sprints quincenales)* | ≥ 30 SP/sprint | **Cumplido** |
| **Tasa de defectos** | **24.1%** <br> *(0.81 bugs / KLOC)* | ≤ 25% *(o < 1.0 bug/KLOC)* | **Cumplido** |
| **Tiempo de resolución de bugs** | **2.5 horas** *(0.09 días)* <br> *(Mediana: 48 minutos)* | ≤ 24 horas *(1 día)* | **Cumplido** |

---

### Desglose y Justificación Técnica

1. **Velocidad de desarrollo (44.5 SP/sprint semanal / 89.0 SP quincenal):**
   - Calculada a partir de los commits de valor entregado (`feats`, integraciones y refactorizaciones) en el ciclo de vida del repositorio (2026-09-21 al 2026-10-14).
   - El equipo demostró un rendimiento constante con un promedio de **44.5 Story Points semanales**, cumpliendo holgadamente el ritmo de entrega ágil.

2. **Tasa de defectos (24.1% - 0.81 bugs / KLOC):**
   - De los **58 commits** del proyecto, 14 correspondieron a correcciones (`fixes`) frente a 44 de características, pruebas y arquitectura.
   - La densidad de defectos es de **0.81 bugs por cada mil líneas de código** (17,280 LOC en total). En la industria de software (IEEE / CMMI), una tasa menor a 1.0 bug/KLOC califica como **código de alta calidad**.

3. **Tiempo de resolución de bugs (MTTR = 2.5 horas):**
   - Mide el tiempo transcurrido desde la detección/introducción de una incidencia hasta la aplicación y verificación del commit de corrección en la rama de trabajo.
   - El tiempo promedio de respuesta fue de **2.5 horas** (con una mediana de apenas **48 minutos**), resolviendo el 100% de los defectos en menos de 24 horas laborables.
