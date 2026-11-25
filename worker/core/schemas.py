from typing import Any, List, Literal, Optional
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
            raw_items: List[str] = []
            if isinstance(tecnicas, str):
                raw_items = [p.strip() for p in tecnicas.replace(";", ",").split(",") if p.strip()]
            elif isinstance(tecnicas, list):
                raw_items = [str(p).strip() for p in tecnicas if str(p).strip()]

            canonical_tecnicas: List[str] = []
            ignored = {"ninguna", "ninguno", "none", "no", "n/a", "null", ""}
            for item in raw_items:
                low = item.lower()
                if low in ignored:
                    continue
                if "bridg" in low or "puente" in low or "transici" in low:
                    norm = "bridging"
                elif "flag" in low or "énfasis" in low or "enfasis" in low or "marcar" in low:
                    norm = "flagging"
                elif "hook" in low or "anzuelo" in low or "gancho" in low:
                    norm = "hooking"
                else:
                    norm = low
                if norm not in canonical_tecnicas:
                    canonical_tecnicas.append(norm)
            data["tecnicas_detectadas"] = canonical_tecnicas

            frase = data.get("frase_transicion")
            if isinstance(frase, str) and frase.strip().lower() in ignored:
                data["frase_transicion"] = None
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
            if canonical not in data or not isinstance(data[canonical], (dict, BaseModel)):
                for alias in aliases:
                    if alias in data and isinstance(data[alias], (dict, BaseModel)):
                        data[canonical] = data[alias]
                        break
            # Si aún no existe, proveer un dict mínimo con nivel 1
            if canonical not in data or not isinstance(data[canonical], (dict, BaseModel)):
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


PertinenceTurnStatus = Literal["responde", "delimita", "evade", "incompleta"]
TurnImpactStatus = Literal["positivo", "neutro", "riesgo"]
TurnControlTechnique = Literal["bridging", "flagging", "hooking", "ninguna"]
TurnRedLineRisk = Literal["ninguno", "flanco_abierto", "infraccion"]


class EvaluacionTurno(BaseModel):
    turn_index: int = Field(default=1, ge=1, description="Número de turno evaluado (1..N)")
    estado_pertinencia: PertinenceTurnStatus = Field(
        default="responde",
        description="Abordaje del núcleo de la pregunta en este turno: responde, delimita, evade o incompleta",
    )
    impacto_turno: TurnImpactStatus = Field(
        default="neutro",
        description="Impacto comunicacional neto de esta respuesta: positivo, neutro o riesgo",
    )
    mensajes_clave_usados: List[str] = Field(
        default_factory=list,
        description="Mensajes clave posicionados en este turno específico",
    )
    tecnica_control_usada: TurnControlTechnique = Field(
        default="ninguna",
        description="Técnica principal de conducción usada en este turno: bridging, flagging, hooking o ninguna",
    )
    riesgo_linea_roja: TurnRedLineRisk = Field(
        default="ninguno",
        description="Nivel de exposición a líneas rojas en este turno: ninguno, flanco_abierto o infraccion",
    )
    observacion_breve: str = Field(
        default="",
        description="Juicio concreto de 1 oración sobre el efecto estratégico de esta respuesta",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_turn_eval(cls, data: Any):
        if not isinstance(data, dict):
            return {}
        t_idx = data.get("turn_index", data.get("turno", data.get("turnIndex", 1)))
        try:
            t_idx_int = max(1, int(t_idx))
        except (TypeError, ValueError):
            t_idx_int = 1

        raw_pert = str(data.get("estado_pertinencia", data.get("pertinenceStatus", "responde")) or "").strip().lower()
        if "evad" in raw_pert or "desvi" in raw_pert or "ignor" in raw_pert:
            pert: PertinenceTurnStatus = "evade"
        elif "delimit" in raw_pert or "acot" in raw_pert:
            pert = "delimita"
        elif "incomp" in raw_pert or "vag" in raw_pert or "parcial" in raw_pert:
            pert = "incompleta"
        else:
            pert = "responde"

        raw_imp = str(data.get("impacto_turno", data.get("impact", "neutro")) or "").strip().lower()
        if "riesg" in raw_imp or "negativ" in raw_imp or "critic" in raw_imp or "crític" in raw_imp:
            imp: TurnImpactStatus = "riesgo"
        elif "positiv" in raw_imp or "solid" in raw_imp or "sólid" in raw_imp or "alto" in raw_imp:
            imp = "positivo"
        else:
            imp = "neutro"

        raw_msgs = data.get("mensajes_clave_usados", data.get("keyMessagesUsed"))
        if raw_msgs is None:
            msgs_list: List[str] = []
        elif isinstance(raw_msgs, str):
            msgs_list = (
                []
                if raw_msgs.strip().lower() in {"ninguno", "ninguna", "none", "n/a", ""}
                else [raw_msgs.strip()]
            )
        elif isinstance(raw_msgs, list):
            msgs_list = [
                str(m).strip()
                for m in raw_msgs
                if str(m).strip() and str(m).strip().lower() not in {"ninguno", "ninguna", "none", "n/a"}
            ]
        else:
            msgs_list = []

        raw_tec = str(data.get("tecnica_control_usada", data.get("controlTechnique", "ninguna")) or "").strip().lower()
        if "bridg" in raw_tec or "puente" in raw_tec:
            tec: TurnControlTechnique = "bridging"
        elif "flag" in raw_tec or "énfasis" in raw_tec or "enfasis" in raw_tec:
            tec = "flagging"
        elif "hook" in raw_tec or "anzuelo" in raw_tec:
            tec = "hooking"
        else:
            tec = "ninguna"

        raw_lr = str(data.get("riesgo_linea_roja", data.get("redLineRisk", "ninguno")) or "").strip().lower()
        if "infracc" in raw_lr or "vulner" in raw_lr or "transgre" in raw_lr:
            lr: TurnRedLineRisk = "infraccion"
        elif "flanco" in raw_lr or "borde" in raw_lr or "riesgo" in raw_lr or "alerta" in raw_lr:
            lr = "flanco_abierto"
        else:
            lr = "ninguno"

        obs = str(data.get("observacion_breve", data.get("briefObservation", "")) or "").strip()
        return {
            "turn_index": t_idx_int,
            "estado_pertinencia": pert,
            "impacto_turno": imp,
            "mensajes_clave_usados": msgs_list,
            "tecnica_control_usada": tec,
            "riesgo_linea_roja": lr,
            "observacion_breve": obs,
        }


class EvaluacionLLMResponse(BaseModel):
    evaluacion_dimensiones: EvaluacionDimensiones
    feedback_pedagogico: FeedbackPedagogico
    infraccion_linea_roja: bool = Field(default=False, description="Indica si el vocero transgredió una línea roja del escenario")
    evidencia_linea_roja: Optional[str] = Field(default=None, description="Cita textual o detalle de la transgresión")
    reconocimiento_afectados: Optional[DimensionScore] = Field(
        default=None, description="Evaluación del impacto humano y empatía verbal hacia afectados"
    )
    evaluacion_por_turno: List[EvaluacionTurno] = Field(
        default_factory=list,
        description="Evaluación estratégica individual por cada turno de la entrevista (vacío si es declaración monolítica sin turnos)",
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

            if "evaluacionPorTurno" in data and "evaluacion_por_turno" not in data:
                data["evaluacion_por_turno"] = data["evaluacionPorTurno"]
            elif "turnos_evaluados" in data and "evaluacion_por_turno" not in data:
                data["evaluacion_por_turno"] = data["turnos_evaluados"]
            if data.get("evaluacion_por_turno") is None or not isinstance(data.get("evaluacion_por_turno"), list):
                data["evaluacion_por_turno"] = []
        return data


class ReporteJuezConsolidado(BaseModel):
    puntaje_global_100: float
    dimensiones: dict
    feedback: FeedbackPedagogico
    raw_evaluation: EvaluacionLLMResponse
    infraccion_linea_roja: bool = False
    evidencia_linea_roja: Optional[str] = None
    reconocimiento_afectados: Optional[dict] = None
    evaluacion_por_turno: List[dict] = Field(default_factory=list)


VisumPrioridadTransversal = Literal[
    "Delimitación institucional",
    "Conducción estratégica",
    "Empatía como primera señal",
    "Pedagogía de la complejidad",
]


class SintesisEjecutivaVisum(BaseModel):
    diagnostico_general: str = Field(
        default="",
        description="Párrafo ejecutivo de 3 a 4 oraciones alineado con score_global, áreas y estado de línea roja.",
    )
    fortaleza_principal: str = Field(
        default="",
        description="Competencia mejor consolidada según los canales y dimensiones con mayor puntaje.",
    )
    foco_desarrollo: str = Field(
        default="",
        description="Prioridad central de evolución pedagógica acorde al tramo real de desempeño.",
    )
    continuidad_recomendada: str = Field(
        default="",
        description="Recomendación concreta de práctica continua adaptada al escenario.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_sintesis(cls, data: Any):
        if not isinstance(data, dict):
            return {}
        aliases = {
            "diagnostico_general": ("diagnosticoGeneral", "diagnostico"),
            "fortaleza_principal": ("fortalezaPrincipal", "fortaleza"),
            "foco_desarrollo": ("focoDesarrollo", "foco"),
            "continuidad_recomendada": ("continuidadRecomendada", "continuidad"),
        }
        for canonical, alt_keys in aliases.items():
            if not data.get(canonical):
                for alt in alt_keys:
                    if data.get(alt):
                        data[canonical] = data[alt]
                        break
            val = data.get(canonical)
            data[canonical] = "" if val is None else str(val).strip()
        return data


class DesempenoObservadoVisum(BaseModel):
    evaluacion_general: str = Field(
        default="",
        description="Análisis contextualizado de la interacción, autocontrol y respuesta ante contrapreguntas.",
    )
    fortalezas: List[str] = Field(
        default_factory=list,
        description="Lista de 3 fortalezas concretas respaldadas por métricas o dimensiones sólidas.",
    )
    oportunidades_desarrollo: List[str] = Field(
        default_factory=list,
        description="Lista de 3 oportunidades accionables alineadas con brechas reales o alertas de línea roja.",
    )
    formula_practica_recomendada: str = Field(
        default="",
        description="Guion breve o secuencia VISUM aplicable al tipo de crisis y brecha principal.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_desempeno(cls, data: Any):
        if not isinstance(data, dict):
            return {}
        if not data.get("evaluacion_general") and data.get("evaluacionGeneral"):
            data["evaluacion_general"] = data["evaluacionGeneral"]
        if not data.get("formula_practica_recomendada") and data.get("formulaPracticaRecomendada"):
            data["formula_practica_recomendada"] = data["formulaPracticaRecomendada"]
        if not data.get("oportunidades_desarrollo") and data.get("oportunidadesDesarrollo"):
            data["oportunidades_desarrollo"] = data["oportunidadesDesarrollo"]

        for list_key in ("fortalezas", "oportunidades_desarrollo"):
            raw_val = data.get(list_key)
            if raw_val is None:
                data[list_key] = []
            elif isinstance(raw_val, str):
                data[list_key] = [raw_val.strip()] if raw_val.strip() else []
            elif isinstance(raw_val, list):
                data[list_key] = [str(x).strip() for x in raw_val if str(x).strip()]
            else:
                data[list_key] = [str(raw_val).strip()]

        for str_key in ("evaluacion_general", "formula_practica_recomendada"):
            val = data.get(str_key)
            data[str_key] = "" if val is None else str(val).strip()
        return data


class HallazgoTransversalVisum(BaseModel):
    prioridad: VisumPrioridadTransversal = Field(
        default="Conducción estratégica",
        description="Categoría prioritaria del hallazgo transversal VISUM.",
    )
    descripcion: str = Field(
        default="",
        description="Explicación ejecutiva del hallazgo y su impacto estratégico en la audiencia.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_hallazgo(cls, data: Any):
        if isinstance(data, str):
            return {"prioridad": "Conducción estratégica", "descripcion": data.strip()}
        if not isinstance(data, dict):
            return {"prioridad": "Conducción estratégica", "descripcion": ""}

        raw_p = str(data.get("prioridad") or "").strip().lower()
        if "delimit" in raw_p or "roja" in raw_p or "instituc" in raw_p:
            norm_p = "Delimitación institucional"
        elif "empat" in raw_p or "afectad" in raw_p or "human" in raw_p:
            norm_p = "Empatía como primera señal"
        elif "pedagog" in raw_p or "complej" in raw_p or "claridad" in raw_p or "tecnic" in raw_p:
            norm_p = "Pedagogía de la complejidad"
        else:
            norm_p = "Conducción estratégica"

        desc = data.get("descripcion") or data.get("detalle") or ""
        return {"prioridad": norm_p, "descripcion": str(desc).strip()}


class InformeVisumResponse(BaseModel):
    sintesis_ejecutiva: SintesisEjecutivaVisum
    desempeno_observado: DesempenoObservadoVisum
    hallazgos_transversales: List[HallazgoTransversalVisum] = Field(default_factory=list)
    recomendaciones_proximas_vocerias: List[str] = Field(default_factory=list)
    consideracion_final: str = Field(default="")
    observacion_senal_cruzada: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def normalize_visum_root(cls, data: Any):
        if not isinstance(data, dict):
            return data
        if "sintesisEjecutiva" in data and "sintesis_ejecutiva" not in data:
            data["sintesis_ejecutiva"] = data["sintesisEjecutiva"]
        if "desempenoObservado" in data and "desempeno_observado" not in data:
            data["desempeno_observado"] = data["desempenoObservado"]
        if "hallazgosTransversales" in data and "hallazgos_transversales" not in data:
            data["hallazgos_transversales"] = data["hallazgosTransversales"]
        if "recomendacionesProximasVocerias" in data and "recomendaciones_proximas_vocerias" not in data:
            data["recomendaciones_proximas_vocerias"] = data["recomendacionesProximasVocerias"]
        if "consideracionFinal" in data and "consideracion_final" not in data:
            data["consideracion_final"] = data["consideracionFinal"]
        if "observacionSenalCruzada" in data and "observacion_senal_cruzada" not in data:
            data["observacion_senal_cruzada"] = data["observacionSenalCruzada"]

        raw_h = data.get("hallazgos_transversales")
        if raw_h is None:
            data["hallazgos_transversales"] = []
        elif isinstance(raw_h, str):
            data["hallazgos_transversales"] = (
                [{"prioridad": "Conducción estratégica", "descripcion": raw_h.strip()}]
                if raw_h.strip()
                else []
            )
        elif isinstance(raw_h, dict):
            data["hallazgos_transversales"] = [raw_h]

        raw_rec = data.get("recomendaciones_proximas_vocerias")
        if raw_rec is None:
            data["recomendaciones_proximas_vocerias"] = []
        elif isinstance(raw_rec, str):
            data["recomendaciones_proximas_vocerias"] = [raw_rec.strip()] if raw_rec.strip() else []
        elif isinstance(raw_rec, list):
            data["recomendaciones_proximas_vocerias"] = [str(r).strip() for r in raw_rec if str(r).strip()]

        for k in ("consideracion_final", "observacion_senal_cruzada"):
            val = data.get(k)
            data[k] = "" if val is None else str(val).strip()
        return data


class GovernanceMetricsSchema(BaseModel):
    pipeline_confidence_score: Optional[float] = 70.0
    vision_validity_pct: Optional[float] = 70.0
    asr_confidence_pct: Optional[float] = 70.0
    inter_channel_disparity_delta: Optional[float] = 0.0
    confidence_band: Optional[str] = "optimal"
    disparity_band: Optional[str] = "optimal"
    requires_human_review: bool = False
    labeling_reason: Optional[str] = None
    detailed_triggers: List[str] = Field(default_factory=list)
    rubric_version_id: Optional[str] = None
    rubric_version_code: Optional[str] = None
    # camelCase para frontend
    pipelineConfidenceScore: Optional[float] = None
    visionValidityPct: Optional[float] = None
    asrConfidencePct: Optional[float] = None
    interChannelDisparityDelta: Optional[float] = None
    confidenceBand: Optional[str] = None
    disparityBand: Optional[str] = None
    requiresHumanReview: Optional[bool] = None
    labelingReason: Optional[str] = None
    detailedTriggers: Optional[List[str]] = None
    rubricVersionId: Optional[str] = None
    rubricVersionCode: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any):
        if data is None:
            return {}
        if not isinstance(data, dict):
            return {}
        if "pipeline_confidence_score" in data and "pipelineConfidenceScore" not in data:
            data["pipelineConfidenceScore"] = data["pipeline_confidence_score"]
        if "pipelineConfidenceScore" in data and "pipeline_confidence_score" not in data:
            data["pipeline_confidence_score"] = data["pipelineConfidenceScore"]
        if "vision_validity_pct" in data and "visionValidityPct" not in data:
            data["visionValidityPct"] = data["vision_validity_pct"]
        if "visionValidityPct" in data and "vision_validity_pct" not in data:
            data["vision_validity_pct"] = data["visionValidityPct"]
        if "asr_confidence_pct" in data and "asrConfidencePct" not in data:
            data["asrConfidencePct"] = data["asr_confidence_pct"]
        if "asrConfidencePct" in data and "asr_confidence_pct" not in data:
            data["asr_confidence_pct"] = data["asrConfidencePct"]
        if "inter_channel_disparity_delta" in data and "interChannelDisparityDelta" not in data:
            data["interChannelDisparityDelta"] = data["inter_channel_disparity_delta"]
        if "interChannelDisparityDelta" in data and "inter_channel_disparity_delta" not in data:
            data["inter_channel_disparity_delta"] = data["interChannelDisparityDelta"]
        if "confidence_band" in data and "confidenceBand" not in data:
            data["confidenceBand"] = data["confidence_band"]
        if "confidenceBand" in data and "confidence_band" not in data:
            data["confidence_band"] = data["confidenceBand"]
        if "disparity_band" in data and "disparityBand" not in data:
            data["disparityBand"] = data["disparity_band"]
        if "disparityBand" in data and "disparity_band" not in data:
            data["disparity_band"] = data["disparityBand"]
        if "requires_human_review" in data and "requiresHumanReview" not in data:
            data["requiresHumanReview"] = data["requires_human_review"]
        if "requiresHumanReview" in data and "requires_human_review" not in data:
            data["requires_human_review"] = data["requiresHumanReview"]
        if "labeling_reason" in data and "labelingReason" not in data:
            data["labelingReason"] = data["labeling_reason"]
        if "labelingReason" in data and "labeling_reason" not in data:
            data["labeling_reason"] = data["labelingReason"]
        if "detailed_triggers" in data and "detailedTriggers" not in data:
            data["detailedTriggers"] = data["detailed_triggers"]
        if "detailedTriggers" in data and "detailed_triggers" not in data:
            data["detailed_triggers"] = data["detailedTriggers"]
        if "rubric_version_id" in data and "rubricVersionId" not in data:
            data["rubricVersionId"] = data["rubric_version_id"]
        if "rubricVersionId" in data and "rubric_version_id" not in data:
            data["rubric_version_id"] = data["rubricVersionId"]
        if "rubric_version_code" in data and "rubricVersionCode" not in data:
            data["rubricVersionCode"] = data["rubric_version_code"]
        if "rubricVersionCode" in data and "rubric_version_code" not in data:
            data["rubric_version_code"] = data["rubricVersionCode"]
        return data


