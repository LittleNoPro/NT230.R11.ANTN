# Reproduction environment. Samples are NOT baked into the image: mount them read-only.
#   docker build -t glareshell-repro .
#   docker run --rm --gpus all --network none \
#     -v "$PWD/samples:/work/samples:ro" -v "$PWD/data:/work/data" -v "$PWD/results:/work/results" \
#     glareshell-repro bash scripts/reproduce.sh
# --network none: the container never needs the network after build; samples are only parsed, never executed.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends php8.2-cli git unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
COPY scripts scripts
RUN bash scripts/setup_tools.sh
COPY src src
