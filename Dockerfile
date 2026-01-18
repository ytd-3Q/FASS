FROM node:20-bookworm-slim AS webui-build
WORKDIR /work/webui
COPY webui/package.json webui/package-lock.json* ./
RUN npm install
COPY webui/ ./
RUN npm run build

FROM python:3.12-slim AS app
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g; s|http://security.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cargo \
    rustc \
    && rm -rf /var/lib/apt/lists/*

COPY fass_gateway/requirements.txt /app/fass_gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/fass_gateway/requirements.txt

COPY memoscore/ /app/memoscore/
RUN pip install --no-cache-dir /app/memoscore

COPY fass_gateway/ /app/fass_gateway/
COPY --from=webui-build /work/webui/dist/ /app/webui/dist/

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "fass_gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
