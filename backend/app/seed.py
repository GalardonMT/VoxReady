"""Seed script: `python -m app.seed` loads the demo dataset (idempotent)."""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app import db as db_module
from app.models.base import Base
from app.models.content import (
    Question,
    Scenario,
    Topic,
    TopicKeyMessage,
    TopicRedLine,
)
from app.models.identity import AppUser, Client
from app.models.privacy import RetentionPolicy
from app.models.progress import Microlesson
from app.models.rubric import RubricArea, RubricDescriptor, RubricVersion
from app.utils import utcnow

DEMO_CLIENT_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
VOCERO_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ADMIN_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
MASTER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")

VOCERO_EMAIL = "vocero@demo.voxready.io"
ADMIN_EMAIL = "admin@demo.voxready.io"
MASTER_EMAIL = "master@voxready.io"

RUBRIC_AREAS = [
    {
        "area_key": "expression",
        "name": "Expresión",
        "channel": "imagen/no verbal",
        "criteria": "Contacto visual, gestos, postura y lenguaje corporal.",
        "weight": 25,
        "descriptors": {
            "high": "Contacto visual sostenido, gestos abiertos y postura segura.",
            "medium": "Contacto visual intermitente; algunos gestos distractores.",
            "low": "Evita la cámara, postura cerrada, gestos nerviosos constantes.",
        },
    },
    {
        "area_key": "voice",
        "name": "Voz",
        "channel": "voz/prosodia",
        "criteria": "Ritmo, tono, pausas y control de muletillas.",
        "weight": 25,
        "descriptors": {
            "high": "Ritmo pausado, tono firme, casi sin muletillas.",
            "medium": "Ritmo irregular; muletillas ocasionales bajo presión.",
            "low": "Ritmo acelerado, tono monótono, muletillas frecuentes.",
        },
    },
    {
        "area_key": "coherence",
        "name": "Coherencia",
        "channel": "contenido",
        "criteria": "Cobertura de mensajes clave, respeto de líneas rojas y bridging.",
        "weight": 25,
        "descriptors": {
            "high": "Sostiene los mensajes clave y no cruza líneas rojas.",
            "medium": "Cubre parcialmente los mensajes clave; bridging débil.",
            "low": "Se sale del mensaje o cruza líneas rojas.",
        },
    },
    {
        "area_key": "empathy",
        "name": "Empatía",
        "channel": "señal cruzada",
        "criteria": "Reconocimiento emocional y alineación verbal/no verbal.",
        "weight": 25,
        "descriptors": {
            "high": "Reconoce el impacto y su lenguaje corporal lo respalda.",
            "medium": "Empatía verbal sin respaldo no verbal consistente.",
            "low": "Respuestas frías o defensivas ante el dolor del público.",
        },
    },
]

TOPICS = [
    {
        "name": "Retiro de producto",
        "context": (
            "Se detectó un defecto de seguridad en el lote X-204 del producto "
            "estrella. Los medios presionan por una declaración oficial."
        ),
        "optics": "empathetic",
        "audience": "leadership",
        "languages": ["es", "en"],
        "key_messages": [
            "La seguridad de nuestros clientes es la prioridad absoluta.",
            "Ya iniciamos el retiro voluntario del lote afectado.",
            "Investigamos la causa y publicaremos los resultados.",
        ],
        "red_lines": [
            "No admitir culpa antes de concluir la investigación.",
            "No especular sobre el número de afectados.",
        ],
        "scenario": {
            "title": "Entrevista TV: retiro del lote X-204",
            "category": "reputational",
            "difficulty": "intermediate",
            "estimated_minutes": 15,
            "question_count": 5,
        },
    },
    {
        "name": "Crisis sanitaria",
        "context": (
            "Un brote vinculado a una de las plantas de producción obliga a "
            "comunicar medidas a la comunidad y a la prensa especializada."
        ),
        "optics": "formal",
        "audience": "frontline",
        "languages": ["es"],
        "key_messages": [
            "Colaboramos con las autoridades sanitarias desde el primer momento.",
            "La planta afectada está temporalmente cerrada por precaución.",
        ],
        "red_lines": ["No minimizar el riesgo para la salud pública."],
        "scenario": {
            "title": "Rueda de prensa: brote en planta",
            "category": "health",
            "difficulty": "hard",
            "estimated_minutes": 20,
            "question_count": 6,
        },
    },
    {
        "name": "Falla operativa",
        "context": (
            "Una caída del servicio digital afectó a miles de usuarios durante "
            "varias horas. Se espera una explicación clara y un plan de acción."
        ),
        "optics": "technical",
        "audience": "technical",
        "languages": ["es", "en", "pt"],
        "key_messages": [
            "El servicio ya está restablecido y monitoreado.",
            "Publicaremos un informe técnico con las medidas correctivas.",
        ],
        "red_lines": ["No culpar a proveedores externos sin evidencia."],
        "scenario": {
            "title": "Entrevista técnica: caída del servicio",
            "category": "operational",
            "difficulty": "basic",
            "estimated_minutes": 10,
            "question_count": 4,
        },
    },
]

QUESTION_TEMPLATES = [
    "¿Qué le diría a las personas afectadas en este momento?",
    "¿Quién asume la responsabilidad de lo ocurrido?",
    "¿Por qué tardaron tanto en comunicarlo?",
    "¿Qué garantías puede ofrecer de que no volverá a suceder?",
    "¿Está dispuesto la empresa a compensar a los afectados?",
    "¿Qué medidas concretas ya están en marcha?",
    "¿Cómo responde a las críticas en redes sociales?",
    "¿Cuál es el mensaje más importante que quiere dejar hoy?",
]

MICROLESSONS = [
    ("Técnica del puente (bridging)", "bridging", 4),
    ("Preguntas hostiles", "hostile-questions", 5),
    ("Lenguaje corporal en cámara", "body-language", 3),
    ("Empatía bajo presión", "empathy", 4),
    ("Control de la voz y las pausas", "voice-control", 3),
]


async def seed_data(session: AsyncSession) -> bool:
    """Insert the demo dataset. Returns False if it already exists."""
    if await session.get(Client, DEMO_CLIENT_ID) is not None:
        return False

    client = Client(id=DEMO_CLIENT_ID, name="Cliente Demo", status="active")
    session.add(client)
    await session.flush()

    vocero = AppUser(
        id=VOCERO_ID,
        b2c_object_id="seed-vocero",
        client_id=DEMO_CLIENT_ID,
        email=VOCERO_EMAIL,
        display_name="María Pérez",
        role="spokesperson",
        preferred_language="es",
        status="active",
    )
    admin = AppUser(
        id=ADMIN_ID,
        b2c_object_id="seed-admin",
        client_id=DEMO_CLIENT_ID,
        email=ADMIN_EMAIL,
        display_name="Carlos Gómez",
        role="client_admin",
        preferred_language="es",
        status="active",
    )
    master = AppUser(
        id=MASTER_ID,
        b2c_object_id="seed-master",
        client_id=None,
        email=MASTER_EMAIL,
        display_name="Equipo VoxReady",
        role="master_config",
        preferred_language="es",
        status="active",
    )
    session.add_all([vocero, admin, master])
    await session.flush()

    # Retention policy (default, current version).
    session.add(
        RetentionPolicy(
            client_id=DEMO_CLIENT_ID,
            keep="full_recording",
            term_days=90,
            version_label="ret-2026-01",
            is_current=True,
            effective_from=utcnow(),
            created_by=ADMIN_ID,
        )
    )

    # Published master rubric v0.4.
    rubric = RubricVersion(
        version_label="v0.4",
        status="published",
        notes="Rúbrica inicial del MVP.",
        published_at=utcnow(),
        created_by=MASTER_ID,
        languages=["es", "en", "pt"],
    )
    session.add(rubric)
    await session.flush()
    for index, area_def in enumerate(RUBRIC_AREAS, start=1):
        area = RubricArea(
            rubric_version_id=rubric.id,
            area_key=area_def["area_key"],
            name=area_def["name"],
            channel=area_def["channel"],
            criteria=area_def["criteria"],
            weight=area_def["weight"],
            sort_order=index,
        )
        session.add(area)
        await session.flush()
        for level, description in area_def["descriptors"].items():
            session.add(
                RubricDescriptor(
                    rubric_area_id=area.id, level=level, description=description
                )
            )

    # Topics, scenarios and question bank.
    for topic_def in TOPICS:
        topic = Topic(
            client_id=DEMO_CLIENT_ID,
            name=topic_def["name"],
            context=topic_def["context"],
            optics=topic_def["optics"],
            audience=topic_def["audience"],
            languages=topic_def["languages"],
            status="active",
        )
        session.add(topic)
        await session.flush()
        for i, text in enumerate(topic_def["key_messages"], start=1):
            session.add(TopicKeyMessage(topic_id=topic.id, text=text, sort_order=i))
        for i, text in enumerate(topic_def["red_lines"], start=1):
            session.add(TopicRedLine(topic_id=topic.id, text=text, sort_order=i))
        scenario_def = topic_def["scenario"]
        session.add(
            Scenario(
                topic_id=topic.id,
                client_id=DEMO_CLIENT_ID,
                title=scenario_def["title"],
                category=scenario_def["category"],
                difficulty=scenario_def["difficulty"],
                estimated_minutes=scenario_def["estimated_minutes"],
                question_count=scenario_def["question_count"],
                status="active",
            )
        )
        for text in QUESTION_TEMPLATES:
            session.add(
                Question(
                    client_id=DEMO_CLIENT_ID,
                    topic_id=topic.id,
                    text=f"[{topic.name}] {text}",
                    source="admin",
                    base_language="es",
                    rating_count=0,
                    in_bank=True,
                    status="active",
                )
            )

    # Microlessons.
    for title, tag, minutes in MICROLESSONS:
        session.add(
            Microlesson(
                client_id=DEMO_CLIENT_ID,
                title=title,
                topic_tag=tag,
                duration_minutes=minutes,
                example_content=f"Ejemplo comentado de '{title}'.",
                status="active",
            )
        )

    await session.commit()
    return True


async def main() -> None:
    engine = db_module.init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db_module.new_session() as session:
        created = await seed_data(session)
    await engine.dispose()
    if created:
        print("Datos semilla cargados: cliente demo, 3 usuarios, rúbrica v0.4.")
    else:
        print("Los datos semilla ya existían; no se hicieron cambios.")


if __name__ == "__main__":
    asyncio.run(main())
