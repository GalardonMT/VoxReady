"""Consultas de solo lectura para el catálogo del administrador del cliente."""

import uuid

from fastapi import HTTPException, Response
from pydantic import BaseModel, Field


class ClientScenarioSummary(BaseModel):
    id: str
    title: str
    category: str
    difficulty: str
    estimatedMinutes: int
    questionCount: int
    audience: str
    optics: str


class ClientScenarioListResponse(BaseModel):
    items: list[ClientScenarioSummary]
    page: int
    pageSize: int
    total: int


class ClientScenarioQuestion(BaseModel):
    sequenceNo: int = Field(ge=1)
    text: str


class ClientScenarioDetail(ClientScenarioSummary):
    context: str
    keyMessages: list[str]
    redLines: list[str]
    questions: list[ClientScenarioQuestion]


def mark_private_no_store(response: Response):
    """Evita conservar en caché contenido interno de escenarios autenticados."""
    response.headers["Cache-Control"] = "private, no-store"


def require_client_admin(profile):
    """Autoriza exclusivamente el rol resuelto desde ``app_user``."""
    if profile.get("role") != "client_admin" or not profile.get("client_id"):
        raise HTTPException(403, "Se requiere el rol client_admin con una empresa asignada.")
    return str(profile["client_id"])


def _scenario_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, "Identificador UUID inválido.") from None


def _summary(row):
    return {
        "id": str(row[0]),
        "title": row[1],
        "category": row[2],
        "difficulty": row[3],
        "estimatedMinutes": row[4],
        "questionCount": row[5],
        "audience": row[6],
        "optics": row[7],
    }


def _availability_where():
    return """s.client_id = ?
              AND s.status = 'active' AND t.status = 'active' AND c.status = 'active'
              AND s.is_deleted = 0 AND t.is_deleted = 0 AND c.is_deleted = 0"""


def list_available(cursor, client_id, page=1, page_size=20):
    """Lista escenarios disponibles, siempre limitados a una empresa."""
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, "Paginación inválida.")

    availability = _availability_where()
    cursor.execute(
        f"""SELECT COUNT_BIG(*)
            FROM dbo.scenario s
            JOIN dbo.topic t ON t.id = s.topic_id
            JOIN dbo.client c ON c.id = s.client_id
            WHERE {availability}""",
        str(client_id),
    )
    count_row = cursor.fetchone()
    total = int(count_row[0]) if count_row else 0

    offset = (page - 1) * page_size
    cursor.execute(
        f"""SELECT s.id, s.title, s.category, s.difficulty,
                   s.estimated_minutes AS estimatedMinutes,
                   (SELECT COUNT(*)
                    FROM dbo.scenario_question sq
                    JOIN dbo.question q ON q.id = sq.question_id
                    WHERE sq.scenario_id = s.id AND sq.status = 'active'
                      AND q.status = 'active' AND q.is_deleted = 0) AS questionCount,
                   t.audience, t.optics
            FROM dbo.scenario s
            JOIN dbo.topic t ON t.id = s.topic_id
            JOIN dbo.client c ON c.id = s.client_id
            WHERE {availability}
            ORDER BY s.created_at DESC, s.id
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        str(client_id),
        offset,
        page_size,
    )
    return {
        "items": [_summary(row) for row in cursor.fetchall()],
        "page": page,
        "pageSize": page_size,
        "total": total,
    }


def get_available(cursor, client_id, scenario_id):
    """Devuelve el detalle funcional sin identificadores ni metadatos internos."""
    scenario_id = _scenario_id(scenario_id)
    client_id = str(client_id)
    cursor.execute(
        """SELECT s.id, s.title, s.category, s.difficulty,
                  s.estimated_minutes AS estimatedMinutes,
                  (SELECT COUNT(*)
                   FROM dbo.scenario_question sq
                   JOIN dbo.question q ON q.id = sq.question_id
                   WHERE sq.scenario_id = s.id AND sq.status = 'active'
                     AND q.status = 'active' AND q.is_deleted = 0) AS questionCount,
                  t.audience, t.optics, t.context
           FROM dbo.scenario s
           JOIN dbo.topic t ON t.id = s.topic_id
           JOIN dbo.client c ON c.id = s.client_id
           WHERE s.id = ? AND s.client_id = ?
             AND s.status = 'active' AND t.status = 'active' AND c.status = 'active'
             AND s.is_deleted = 0 AND t.is_deleted = 0 AND c.is_deleted = 0""",
        scenario_id,
        client_id,
    )
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Escenario no disponible.")

    detail = _summary(row)
    detail["context"] = row[8]

    cursor.execute(
        """SELECT message.text
           FROM dbo.topic_key_message message
           JOIN dbo.topic t ON t.id = message.topic_id
           JOIN dbo.scenario s ON s.topic_id = t.id
           JOIN dbo.client c ON c.id = s.client_id
           WHERE s.id = ? AND s.client_id = ?
             AND s.status = 'active' AND t.status = 'active' AND c.status = 'active'
             AND s.is_deleted = 0 AND t.is_deleted = 0 AND c.is_deleted = 0
             AND message.status = 'active'
           ORDER BY message.sort_order, message.id""",
        scenario_id,
        client_id,
    )
    detail["keyMessages"] = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        """SELECT red_line.text
           FROM dbo.topic_red_line red_line
           JOIN dbo.topic t ON t.id = red_line.topic_id
           JOIN dbo.scenario s ON s.topic_id = t.id
           JOIN dbo.client c ON c.id = s.client_id
           WHERE s.id = ? AND s.client_id = ?
             AND s.status = 'active' AND t.status = 'active' AND c.status = 'active'
             AND s.is_deleted = 0 AND t.is_deleted = 0 AND c.is_deleted = 0
             AND red_line.status = 'active'
           ORDER BY red_line.sort_order, red_line.id""",
        scenario_id,
        client_id,
    )
    detail["redLines"] = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        """SELECT q.id, sq.sequence_no AS sequenceNo, q.text
           FROM dbo.scenario_question sq
           JOIN dbo.question q ON q.id = sq.question_id
           JOIN dbo.scenario s ON s.id = sq.scenario_id
           JOIN dbo.topic t ON t.id = s.topic_id
           JOIN dbo.client c ON c.id = s.client_id
           WHERE s.id = ? AND s.client_id = ?
             AND s.status = 'active' AND t.status = 'active' AND c.status = 'active'
             AND s.is_deleted = 0 AND t.is_deleted = 0 AND c.is_deleted = 0
             AND sq.status = 'active'
             AND q.status = 'active' AND q.is_deleted = 0
           ORDER BY sq.sequence_no""",
        scenario_id,
        client_id,
    )
    detail["questions"] = [
        {"sequenceNo": row[1], "text": row[2]} for row in cursor.fetchall()
    ]
    return detail
