FROM python:3.12-slim

WORKDIR /app

# Install build tools needed for some Python packages (pycairo via xhtml2pdf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libcairo2-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/        ./api/
COPY core/       ./core/
COPY forge/      ./forge/
COPY scenarios/  ./scenarios/
COPY scripts/    ./scripts/

# Session persistence directory
RUN mkdir -p data/sessions data/theories/pending

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
