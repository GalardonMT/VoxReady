FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias para compilar pyodbc y repo oficial de Microsoft ODBC Driver 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc-dev \
    gcc \
    g++ \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

FROM base AS application
COPY main.py master_topics.py spokesperson_store.py progress_store.py schedule_store.py microlessons.py client_store.py microlesson_assignment_migration.py metrics_catalog.py metrics_migration.py metrics_store.py ./
COPY schemas ./schemas
COPY services ./services
COPY scripts ./scripts

FROM application AS test
COPY tests ./tests
CMD ["python", "-m", "pytest", "tests/test_clients.py", "tests/test_clients_azure.py", "tests/test_master_topics_azure.py", "tests/test_microlessons_azure.py", "tests/test_microlesson_assignment_migration.py", "tests/test_microlesson_assignments_routes.py", "tests/test_flow_regression.py", "tests/test_progress_migration.py", "tests/test_progress_store.py", "tests/test_schedule_store.py", "tests/test_progress_schedule_routes.py", "tests/test_metrics_editor.py", "-q", "-p", "no:cacheprovider"]

FROM application AS runtime

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
