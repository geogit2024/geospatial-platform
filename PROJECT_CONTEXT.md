# PROJECT_CONTEXT

## Project Objective
Build and operate a geospatial publishing platform that ingests raster/vector data, processes assets with Python workers (GDAL/geospatial pipeline), and publishes interoperable OGC services (WMS/WMTS/WCS/WFS) via GeoServer.

## Tech Stack
- Backend API: Python, FastAPI, Uvicorn, SQLAlchemy (async), Pydantic Settings
- Worker: Python async worker, Redis Streams, GDAL/GeoPandas pipeline, GeoServer REST integration
- Frontend: Next.js 14, React 18, TypeScript, Tailwind
- Infra/Runtime: Docker Compose, PostgreSQL, Redis, MinIO, GeoServer

## Architecture Overview
1. Client requests signed upload URL from API.
2. Asset is uploaded to object storage (MinIO in dev; GCS in production).
3. API/queue event triggers worker processing.
4. Worker normalizes/processes data and stores processed output.
5. Worker publishes layer/store in GeoServer.
6. API exposes metadata and OGC endpoints to frontend/clients.

## Key Modules
- `api/`: FastAPI orchestration, models, routers, services, metrics, auth-related API behavior
- `worker/`: queue consumers, raster/vector processing pipeline, GeoServer publication and recovery flows
- `frontend/`: Next.js app and dashboard/UI pages
- `tests/`: API/processing/metrics behavior tests
- `geoserver/`, `minio/`: service-specific helper scripts/config
- `context/`: architecture and system documentation

---

## DEV — Deploy local (Docker Compose)

### Stack local
| Serviço    | URL local                          |
|------------|------------------------------------|
| Frontend   | http://localhost:3000              |
| API        | http://localhost:8000              |
| GeoServer  | http://localhost:8080/geoserver    |
| PostgreSQL | localhost:5432                     |
| Redis      | localhost:6379                     |

### Subir o ambiente pela primeira vez
```bash
# 1. Configurar variáveis
cp .env.example .env   # ajustar valores conforme necessário

# 2. Subir todos os serviços
docker compose up --build
```

### Rebuild após mudanças de código
```bash
# Apenas API
docker compose up --build api

# Apenas worker
docker compose up --build worker

# Apenas frontend
docker compose up --build frontend

# Tudo
docker compose up --build
```

### Outros comandos úteis
```bash
docker compose logs -f          # acompanhar logs
docker compose down             # parar todos os serviços
docker compose down -v          # parar e remover volumes
```

### Arquivos relevantes
- `docker-compose.yml` — definição dos serviços
- `Dockerfile.api` — imagem da API
- `Dockerfile.worker` — imagem do worker
- `frontend/Dockerfile` — imagem do frontend (multi-stage: dev / builder / runner)
- `.env` — variáveis de ambiente locais (não commitar)

---

## PROD — Deploy Google Cloud Platform (GCP)

### Projeto GCP
- **Project ID:** `geopublish`
- **GCP Account:** `admin@novaterrageo.com.br`
- **Região:** `us-central1`

### Serviços Cloud Run
| Serviço                  | Revisão mais recente               | URL                                                              |
|--------------------------|------------------------------------|------------------------------------------------------------------|
| `geopublish-api`         | `geopublish-api-00109-pnw`         | https://geopublish-api-758336857324.us-central1.run.app          |
| `geopublish-frontend`    | `geopublish-frontend-00061-xvb`    | https://geopublish-frontend-758336857324.us-central1.run.app     |
| `geopublish-worker-service` | `geopublish-worker-service-00001-xzc` | https://geopublish-worker-service-758336857324.us-central1.run.app |
| `geopublish-worker-job`  | —                                  | Cloud Run Job (execução sob demanda)                             |

### Artifact Registry
- **Repositório:** `cloud-run-source-deploy`
- **Caminho das imagens:** `us-central1-docker.pkg.dev/geopublish/cloud-run-source-deploy/<service>:<sha>`

### Pipeline de deploy (prod)
Arquivo: `infra/cloudbuild/prod.yaml`

O pipeline: builda API + worker + frontend → publica imagens no Artifact Registry → deploya os 4 serviços no Cloud Run.

### Comando para deploy em produção
```bash
# Obter o SHA do commit atual
SHORT_SHA=$(git rev-parse --short HEAD)

# Disparar o pipeline
gcloud builds submit \
  --config infra/cloudbuild/prod.yaml \
  --substitutions=_REGION=us-central1,_REPOSITORY=cloud-run-source-deploy,SHORT_SHA=$SHORT_SHA
```

> **IMPORTANTE:** `SHORT_SHA` deve sempre ser passado explicitamente — não é preenchido automaticamente em submissões manuais.

### Pré-requisitos antes de deployar em prod
1. Commitar e pushar todas as mudanças no branch atual.
2. Verificar autenticação: `gcloud auth list` (conta ativa: `admin@novaterrageo.com.br`).
3. Verificar projeto ativo: `gcloud config get-value project` (deve retornar `geopublish`).

### Verificar status do deploy
```bash
# Listar builds recentes
gcloud builds list --limit=5 --format="table(id,status,createTime,duration)" --project=geopublish

# Acompanhar log de um build específico
gcloud builds log <BUILD_ID> --project=geopublish
```

### Quirks conhecidos
- O `.dockerignore` raiz exclui `worker/` (otimizado para build da API). O build do worker usa `DOCKER_BUILDKIT=1` para forçar o uso do `Dockerfile.worker.dockerignore`, que inclui `worker/`.
- O `_REPOSITORY` padrão no `prod.yaml` é `geopublish` (nome incorreto) — sempre sobrescrever com `cloud-run-source-deploy`.

---

## Development Rules
- Keep business logic in `api/` and `worker/`; do not duplicate processing logic in frontend.
- Use `.env` at repository root as the single local environment source.
- Prefer local virtual environment (`.venv`) for Python and local `frontend/node_modules` for Node.js.
- Docker is the default local execution path for development parity.
- After code changes, rebuild and rerun containers via workspace Docker tasks.
- Use local `.venv` run/debug only as an optional fallback for isolated debugging.
- Do not commit credentials or generated secrets.

## Environment Isolation
- Python interpreter target: `./.venv/Scripts/python.exe` (workspace default).
- Python packages: install via `api/requirements.txt` and `worker/requirements.txt` into local `.venv`.
- Node packages: install via `frontend/package-lock.json` with `npm ci`.
- Environment variables: keep in root `.env` (project-specific, not global shell config).
- Runtime services: use `docker compose` for full local stack parity.

## AI Agent Guidance
- Read `PROJECT_CONTEXT.md`, `README.md`, and `context/system_architecture.md` before major changes.
- Preserve module boundaries (`api`, `worker`, `frontend`).
- Favor minimal, reversible configuration changes.
- Validate with module-appropriate tests before proposing merges.
