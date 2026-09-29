FROM python:3.12-slim-bookworm

# Azure SQL uses Microsoft's ODBC 18 driver through aioodbc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg libgssapi-krb5-2 \
    && curl -sSL -o /tmp/packages-microsoft-prod.deb \
    https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
