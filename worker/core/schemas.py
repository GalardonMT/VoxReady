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
    fortaleza_principal: str = Field(default="")
    brecha_critica: str = Field(default="")
    recomendacion_accionable: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def map_feedback_aliases(cls, data: Any):
        if isinstance(data, dict):
            if "fortaleza" in data and not data.get("fortaleza_principal"):
                data["fortaleza_principal"] = str(data["fortaleza"])
            if "brecha" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = str(data["brecha"])
            elif "debilidad" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = str(data["debilidad"])
            elif "area_mejora" in data and not data.get("brecha_critica"):
                data["brecha_critica"] = str(data["area_mejora"])
            if "recomendacion" in data and not data.get("recomendacion_accionable"):
                data["recomendacion_accionable"] = str(data["recomendacion"])
        return data


class EvaluacionLLMResponse(BaseModel):
    evaluacion_dimensiones: EvaluacionDimensiones
    feedback_pedagogico: FeedbackPedagogico

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
            if "dimensiones" in data and "evaluacion_dimensiones" not in data:
                data["evaluacion_dimensiones"] = data["dimensiones"]
            if "feedback" in data and "feedback_pedagogico" not in data:
                data["feedback_pedagogico"] = data["feedback"]
        return data


class ReporteJuezConsolidado(BaseModel):
    puntaje_global_100: float
    dimensiones: dict
    feedback: FeedbackPedagogico
    raw_evaluation: EvaluacionLLMResponse
