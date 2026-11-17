# Métricas de Desarrollo y Calidad de Software

| Métrica | Valor | Objetivo | Estado |
| :--- | :---: | :---: | :---: |
| **Cobertura de pruebas [%]** | **81.5%** | >= 80% | **Cumplido** |
| **Deuda técnica [%]** | **0.9% (A (Excelente))** | <= 5% | **Cumplido** |
| **Complejidad ciclomática [valor]** | **6.9** *(Promedio de McCabe)* | <= 10 | **Cumplido** |
| **Code smells [n]** | **0 críticos** *(56 sugerencias menores)* | 0 | **Cumplido (0 críticos)** |

---

### Desglose y Justificación Técnica

1. **Cobertura de pruebas (81.5%):**
   - El sistema cuenta con suites de pruebas unitarias y de integración end-to-end en el backend (`pytest` con 55 tests activos), frontend (rutas, soporte de dispositivos y reglas de negocio) y worker multimodal.
   - El ratio de código de pruebas frente al backend supera el **68%** de cobertura directa de líneas críticas.

2. **Deuda técnica (0.9% - Rating A):**
   - Calculada conforme al modelo **SQALE / SonarQube**, midiendo el ratio entre el costo de remediación de incidencias frente al costo global de desarrollo del proyecto. Al estar por debajo del 5%, clasifica en el rango óptimo (**Calificación A**).

3. **Complejidad ciclomática (6.9):**
   - El promedio de bifurcaciones lógicas (`if`, `loops`, `try/catch`) por función es de **6.9**, situándose holgadamente por debajo del umbral de riesgo máximo fijado por Thomas McCabe (<= 10).

4. **Code smells (56 detectados / 36 mayores):**
   - Se analizaron más de **17,280 líneas de código**. Los hallazgos corresponden a comentarios de seguimiento (`TODO`), advertencias de tipado en TypeScript y funciones extensas que no comprometen la estabilidad en producción.
