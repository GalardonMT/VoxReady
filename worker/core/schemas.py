from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator


class DimensionScore(BaseModel):
    nivel: int = Field(..., ge=1, le=5, description="Nivel conductual del 1 al 5")
    criterio: str = Field(default="", description="Justificación cualitativa de la calificación asignada")
    evidencia_textual: Optional[str] = Field(None, description="Cita exacta de la transcripción que sustenta el juicio")

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any):
        if isinstance(data, dict):
            # Modelos a veces devuelven 'justificacion' o 'descripcion' en vez de 'criterio'
            if "justificacion" in data and not data.get("criterio"):
                data["criterio"] = data["justificacion"]
            elif "descripcion" in data and not data.get("criterio"):
                data["criterio"] = data["descripcion"]
            # Convertir nivel si viene como string
            if "nivel" in data and isinstance(data["nivel"], str):
                try:
                    data["nivel"] = int(data["nivel"])
                except ValueError:
                    pass
        return data


class TecnicasControlScore(DimensionScore):
    tecnicas_detectadas: List[str] = Field(
        default_factory=list,
        description="Lista de técnicas halladas: bridging, flagging, hooking",
    )
    frase_transicion: Optional[str] = Field(
        None, description="Frase exacta utilizada como puente o énfasis"
    )


class MensajeClaveScore(DimensionScore):
    mensajes_cumplidos: List[str] = Field(default_factory=list)
    mensajes_omitidos: List[str] = Field(default_factory=list)


class EvaluacionDimensiones(BaseModel):
    pertinencia_respuesta: DimensionScore
    tecnicas_control: TecnicasControlScore
    alineacion_mensaje_clave: MensajeClaveScore
    capacidad_sintesis: DimensionScore
    claridad_mensaje: DimensionScore
    consistencia_institucional: DimensionScore
    asertividad_hostilidad: DimensionScore


class FeedbackPedagogico(BaseModel):
    fortaleza_principal: str
    brecha_critica: str
    recomendacion_accionable: str


class EvaluacionLLMResponse(BaseModel):
    evaluacion_dimensiones: EvaluacionDimensiones
    feedback_pedagogico: FeedbackPedagogico


class ReporteJuezConsolidado(BaseModel):
    puntaje_global_100: float
    dimensiones: dict
    feedback: FeedbackPedagogico
    raw_evaluation: EvaluacionLLMResponse
