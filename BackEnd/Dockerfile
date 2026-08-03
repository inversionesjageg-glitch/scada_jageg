FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Instalación de dependencias y Driver con llaves GPG correctas
RUN apt-get update && apt-get install -y \
    curl gnupg unixodbc-dev g++ \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

# 2. SOBRESCRITURA TOTAL de OpenSSL para habilitar TLS 1.0 y Legacy Providers
# Esto elimina cualquier restricción que bloquee el protocolo antiguo
RUN printf "openssl_conf = openssl_init\n\n\
[openssl_init]\n\
providers = provider_sect\n\
ssl_conf = ssl_sect\n\n\
[provider_sect]\n\
default = default_sect\n\
legacy = legacy_sect\n\n\
[default_sect]\n\
activate = 1\n\n\
[legacy_sect]\n\
activate = 1\n\n\
[ssl_sect]\n\
system_default = system_default_sect\n\n\
[system_default_sect]\n\
CipherString = DEFAULT@SECLEVEL=1\n\
MinProtocol = TLSv1\n\
Options = UnsafeLegacyRenegotiation\n" > /etc/ssl/openssl.cnf

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]


