# Credit Evidence Engine — local CLI image
# Primary runtime is venv or docker compose (see docs/WED_GATE.md).
# Not an HTTP server. Not hosted on Axis/OpenShift.

FROM python:3.12-slim

WORKDIR /app

# Install system deps for any native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY scripts ./scripts
COPY packs ./packs
COPY specs ./specs
COPY tests ./tests
COPY docs ./docs

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Make entrypoint executable
RUN chmod +x scripts/docker-entrypoint.sh

# Entrypoint passes args to run_wed_gate.py
ENTRYPOINT ["scripts/docker-entrypoint.sh"]

# Default: stub mode (safe, no API key needed)
CMD ["--stub"]
