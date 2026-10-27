from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class DimensionScore(BaseModel):
    nivel: int = Field(default=1, ge=1, le=5, description="Nivel conductual del 1 al 5")
    criterio: str = Field(default="", description="Justificación cualitativa de la calificación asignada")
    evidencia_textual: Optional[str] = Field(default="", description="Cita exacta de la transcripción que sustenta el juicio")

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any):
        if isinstance(data, dict):
            # Modelos a veces devuelven 'justificacion' o 'descripcion' en vez de 'criterio'
            if "justificacion" in data and not data.get("criterio"):
                data["criterio"] = data["justificacion"]
            elif "descripcion" in data and not data.get("criterio"):
                data["criterio"] = data["descripcion"]

            # Si evidencia_textual viene como lista o bajo clave alternativa
            if "evidencia" in data and not data.get("evidencia_textual"):
                data["evidencia_textual"] = data["evidencia"]
            if isinstance(data.get("evidencia_textual"), list):
                data["evidencia_textual"] = " ".join(str(x) for x in data["evidencia_textual"])

            # Convertir nivel y clampear obligatoriamente a rango [1, 5]
            if "nivel" in data and data["nivel"] is not None:
                try:
                    n = int(round(float(data["nivel"])))
                    data["nivel"] = max(1, min(5, n))
                except (ValueError, TypeError):
                    data["nivel"] = 1
            else:
                data["nivel"] = 1
        return data


class TecnicasControlScore(DimensionScore):
    tecnicas_detectadas: List[str] = Field(
        default_factory=list,
        description="Lista de técnicas halladas: bridging, flagging, hooking",
    )
    frase_transicion: Optional[str] = Field(
        default=None, description="Frase exacta utilizada como puente o énfasis"
    )

    @model_validator(mode="before")
    @classmethod
    def map_tecnicas(cls, data: Any):
        if isinstance(data, dict):
            data = cls.map_aliases(data)
            tecnicas = data.get("tecnicas_detectadas")
            if tecnicas is None:
                data["tecnicas_detectadas"] = []
            elif isinstance(tecnicas, str):
                if tecnicas.lower() in ["ninguna", "ninguno", "none", "no", "n/a", ""]:
                    data["tecnicas_detectadas"] = []
                else:
                    data["tecnicas_detectadas"] = [tecnicas]
        return data


class MensajeClaveScore(DimensionScore):
    mensajes_cumplidos: List[str] = Field(default_factory=list)
    mensajes_omitidos: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def map_mensajes(cls, data: Any):
        if isinstance(data, dict):
            data = cls.map_aliases(data)
            for k in ["mensajes_cumplidos", "mensajes_omitidos"]:
                val = data.get(k)
                if val is None:
                    data[k] = []
                elif isinstance(val, str):
                    if val.lower() in ["ninguno", "ninguna", "none", "n/a", ""]:
                        data[k] = []
                    else:
                        data[k] = [val]
        return data


class EvaluacionDimensiones(BaseModel):
    pertinencia_respuesta: DimensionScore
    tecnicas_control: TecnicasControlScore
    alineacion_mensaje_clave: MensajeClaveScore
    capacidad_sintesis: DimensionScore
    claridad_mensaje: DimensionScore
    consistencia_institucional: DimensionScore
    asertividad_hostilidad: DimensionScore

    @model_validator(mode="before")
    @classmethod
    def normalize_dimension_keys(cls, data: Any):
        if not isinstance(data, dict):
            return data

        key_aliases = {
            "pertinencia_respuesta": ["pertinencia", "pertinencia_de_la_respuesta"],
            "tecnicas_control": ["tecnicas_de_control", "control_crisis", "tecnicas"],
            "alineacion_mensaje_clave": ["alineacion_mensajes_clave", "mensajes_clave", "alineacion_mensaje"],
            "capacidad_sintesis": ["sintesis", "capacidad_de_sintesis"],
            "claridad_mensaje": ["claridad", "claridad_del_mensaje"],
            "consistencia_institucional": ["consistencia", "consistencia_del_mensaje"],
            "asertividad_hostilidad": ["asertividad", "asertividad_y_hostilidad", "tono_asertivo"],
        }

        for canonical, aliases in key_aliases.items():
            if canonical not in data or not isinstance(data[canonical], dict):
                for alias in aliases:
                    if alias in data and isinstance(data[alias], dict):
                        data[canonical] = data[alias]
                        break
            # Si aún no existe, proveer un dict mínimo con nivel 1
            if canonical not in data or not isinstance(data[canonical], dict):
                data[canonical] = {"nivel": 1, "criterio": "No evaluado directamente por el modelo"}

        return data


class FeedbackPedagogico(BaseModel):
    fortaleza_principal: Optional[str] = Field(default="")
    brecha_critica: Optional[str] = Field(default="")
    recomendacion_accionable: Optional[str] = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def map_feedback_aliases(cls, data: Any):
        if isinstance(data, dict):
            if "fortaleza" in data and not data.get("fortaleza_principal"):
                data["fortaleza_principal"] = data["fortaleza"]
            if "brecha" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = data["brecha"]
            elif "debilidad" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = data["debilidad"]
            elif "area_mejora" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = data["area_mejora"]
            if "recomendacion" in data and not data.get("recomendacion_accionable"):
                data["recomendacion_accionable"] = data["recomendacion"]

            # Sanitización de nulos / listas / tipos no string: garantizar string válido
            for k in ["fortaleza_principal", "brecha_critica", "recomendacion_accionable"]:
                val = data.get(k)
                if val is None:
                    data[k] = ""
                elif isinstance(val, list):
                    data[k] = " ".join(str(x) for x in val)
                elif not isinstance(val, str):
                    data[k] = str(val)
        return data


class EvaluacionLLMResponse(BaseModel):
    evaluacion_dimensiones: EvaluacionDimensiones
    feedback_pedagogico: FeedbackPedagogico
    infraccion_linea_roja: bool = Field(default=False, description="Indica si el vocero transgredió una línea roja del escenario")
    evidencia_linea_roja: Optional[str] = Field(default=None, description="Cita textual o detalle de la transgresión")
    reconocimiento_afectados: Optional[DimensionScore] = Field(
        default=None, description="Evaluación del impacto humano y empatía verbal hacia afectados"
    )

    @model_validator(mode="before")
    @classmethod
    def map_root_aliases(cls, data: Any):
        if isinstance(data, dict):
            if "evaluacion" in data and isinstance(data["evaluacion"], dict):
                inner = data["evaluacion"]
                if "evaluacion_dimensiones" in inner:
                    data["evaluacion_dimensiones"] = inner["evaluacion_dimensiones"]
                if "feedback_pedagogico" in inner:
                    data["feedback_pedagogico"] = inner["feedback_pedagogico"]
                if "infraccion_linea_roja" in inner and "infraccion_linea_roja" not in data:
                    data["infraccion_linea_roja"] = inner["infraccion_linea_roja"]
                if "evidencia_linea_roja" in inner and "evidencia_linea_roja" not in data:
                    data["evidencia_linea_roja"] = inner["evidencia_linea_roja"]
                if "reconocimiento_afectados" in inner and "reconocimiento_afectados" not in data:
                    data["reconocimiento_afectados"] = inner["reconocimiento_afectados"]
            if "dimensiones" in data and "evaluacion_dimensiones" not in data:
                data["evaluacion_dimensiones"] = data["dimensiones"]
            if "feedback" in data and "feedback_pedagogico" not in data:
                data["feedback_pedagogico"] = data["feedback"]
            
            # Aliases para líneas rojas
            if "infraccion_lineas_rojas" in data and "infraccion_linea_roja" not in data:
                data["infraccion_linea_roja"] = data["infraccion_lineas_rojas"]
            if "evidencia_lineas_rojas" in data and "evidencia_linea_roja" not in data:
                data["evidencia_linea_roja"] = data["evidencia_lineas_rojas"]
            if "linea_roja_vulnerada" in data and "infraccion_linea_roja" not in data:
                data["infraccion_linea_roja"] = data["linea_roja_vulnerada"]

            # Sanitización robusta de infraccion_linea_roja (soporta bool, dict, str o None)
            raw_infraccion = data.get("infraccion_linea_roja")
            if isinstance(raw_infraccion, dict):
                # Si el LLM devolvió un dict tipo {'boolean': True, 'evidencia': '...'}
                if not data.get("evidencia_linea_roja"):
                    data["evidencia_linea_roja"] = (
                        raw_infraccion.get("evidencia")
                        or raw_infraccion.get("evidencia_textual")
                        or raw_infraccion.get("detalle")
                        or raw_infraccion.get("cita")
                    )
                if "boolean" in raw_infraccion:
                    data["infraccion_linea_roja"] = bool(raw_infraccion["boolean"])
                elif "infraccion" in raw_infraccion:
                    data["infraccion_linea_roja"] = bool(raw_infraccion["infraccion"])
                elif "vulnerada" in raw_infraccion:
                    data["infraccion_linea_roja"] = bool(raw_infraccion["vulnerada"])
                elif "valor" in raw_infraccion:
                    data["infraccion_linea_roja"] = bool(raw_infraccion["valor"])
                elif "resultado" in raw_infraccion:
                    data["infraccion_linea_roja"] = bool(raw_infraccion["resultado"])
                else:
                    data["infraccion_linea_roja"] = True
            elif isinstance(raw_infraccion, str):
                data["infraccion_linea_roja"] = raw_infraccion.strip().lower() in ["true", "1", "si", "sí", "yes"]
            elif raw_infraccion is None:
                data["infraccion_linea_roja"] = False
            else:
                data["infraccion_linea_roja"] = bool(raw_infraccion)

            # Sanitización de evidencia_linea_roja
            if isinstance(data.get("evidencia_linea_roja"), list):
                data["evidencia_linea_roja"] = " ".join(str(x) for x in data["evidencia_linea_roja"])
            elif data.get("evidencia_linea_roja") is not None and not isinstance(data.get("evidencia_linea_roja"), str):
                data["evidencia_linea_roja"] = str(data["evidencia_linea_roja"])
            
            # Aliases y tipos para reconocimiento_afectados
            if "reconocimiento_afectado" in data and "reconocimiento_afectados" not in data:
                data["reconocimiento_afectados"] = data["reconocimiento_afectado"]
            elif "empatia_afectados" in data and "reconocimiento_afectados" not in data:
                data["reconocimiento_afectados"] = data["empatia_afectados"]
            if isinstance(data.get("reconocimiento_afectados"), (int, float)):
                data["reconocimiento_afectados"] = {
                    "nivel": int(data["reconocimiento_afectados"]),
                    "criterio": "Evaluación numérica de empatía hacia afectados.",
                    "evidencia_textual": ""
                }
        return data


class ReporteJuezConsolidado(BaseModel):
    puntaje_global_100: float
    dimensiones: dict
    feedback: FeedbackPedagogico
    raw_evaluation: EvaluacionLLMResponse
    infraccion_linea_roja: bool = False
    evidencia_linea_roja: Optional[str] = None
    reconocimiento_afectados: Optional[dict] = None

