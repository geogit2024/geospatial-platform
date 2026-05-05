# GeoPublish — Instruções para o Agente

Leia este arquivo inteiro antes de qualquer ação. Ele é a fonte primária de contexto para deployar e operar este projeto.

---

## Identidade do projeto

Plataforma SaaS WebGIS (GeoPublish) para ingestão, processamento e publicação de dados geoespaciais raster/vetor. Detalhes completos em `PROJECT_CONTEXT.md`.

---

## DEPLOY — DEV (container local)

Quando o usuário pedir para "subir", "rodar", "atualizar" o ambiente **dev/local**, use Docker Compose.

### Subir tudo
```bash
docker compose up --build
```

### Rebuild de um serviço específico após mudança de código
```bash
docker compose up --build api        # mudanças em api/
docker compose up --build worker     # mudanças em worker/
docker compose up --build frontend   # mudanças em frontend/
```

### URLs locais
| Serviço   | URL                             |
|-----------|---------------------------------|
| Frontend  | http://localhost:3000           |
| API       | http://localhost:8000           |
| GeoServer | http://localhost:8080/geoserver |

### Arquivos Docker
- `docker-compose.yml` — orquestração local
- `Dockerfile.api` — API
- `Dockerfile.worker` — worker
- `frontend/Dockerfile` — frontend (multi-stage)

---

## DEPLOY — PRODUÇÃO (GCP / Google Cloud)

Quando o usuário pedir para "deployar", "publicar", "atualizar produção" ou "atualizar GCP", siga este fluxo **exatamente**.

### Pré-requisitos (verificar sempre)
```bash
gcloud config get-value project   # deve retornar: geopublish
gcloud auth list                  # conta ativa: admin@novaterrageo.com.br
```

### Fluxo completo de deploy em produção

**1. Commitar e pushar as mudanças**
```bash
git add <arquivos>
git commit -m "mensagem"
git push origin <branch>
```

**2. Obter o SHA do commit e disparar o pipeline**
```bash
SHORT_SHA=$(git rev-parse --short HEAD)

gcloud builds submit \
  --config infra/cloudbuild/prod.yaml \
  --substitutions=_REGION=us-central1,_REPOSITORY=cloud-run-source-deploy,SHORT_SHA=$SHORT_SHA
```

> `SHORT_SHA` DEVE ser sempre passado explicitamente — não é preenchido automaticamente em submissões manuais.
> `_REPOSITORY` DEVE ser `cloud-run-source-deploy` — o valor padrão no yaml (`geopublish`) está errado.

**3. Verificar status**
```bash
gcloud builds list --limit=5 --format="table(id,status,createTime,duration)" --project=geopublish
gcloud builds log <BUILD_ID> --project=geopublish
```

### O que o pipeline faz (`infra/cloudbuild/prod.yaml`)
1. Build: API (`Dockerfile.api`) + Worker (`Dockerfile.worker`) + Frontend (`frontend/Dockerfile`)
2. Push das imagens para Artifact Registry: `us-central1-docker.pkg.dev/geopublish/cloud-run-source-deploy/<service>:<SHA>`
3. Deploy no Cloud Run: `geopublish-api`, `geopublish-worker-service`, `geopublish-worker-job`, `geopublish-frontend`

### Serviços Cloud Run em produção
| Serviço                     | URL                                                              |
|-----------------------------|------------------------------------------------------------------|
| `geopublish-frontend`       | https://geopublish-frontend-758336857324.us-central1.run.app    |
| `geopublish-api`            | https://geopublish-api-758336857324.us-central1.run.app         |
| `geopublish-worker-service` | https://geopublish-worker-service-758336857324.us-central1.run.app |

### Quirks conhecidos — NÃO ignore
1. **`.dockerignore` raiz exclui `worker/`** — o build do worker usa `DOCKER_BUILDKIT=1` (já configurado no `prod.yaml`) para usar `Dockerfile.worker.dockerignore` que inclui `worker/`. Nunca remover o `DOCKER_BUILDKIT=1` do step `build-worker`.
2. **`_REPOSITORY` padrão errado** — o `prod.yaml` tem `_REPOSITORY: geopublish` como default, mas o repositório real no Artifact Registry é `cloud-run-source-deploy`. Sempre passar `_REPOSITORY=cloud-run-source-deploy` na linha de comando.
3. **`SHORT_SHA` não é automático** — ao contrário de triggers do Cloud Build, submissões manuais não preenchem `$SHORT_SHA`. Sempre obter com `git rev-parse --short HEAD` e passar como substituição.

---

## Regras gerais
- Lógica de negócio em `api/` e `worker/`; nunca duplicar no frontend.
- `.env` na raiz é a única fonte de variáveis locais — nunca commitar.
- Preservar fronteiras de módulos: `api/`, `worker/`, `frontend/`.
- Mudanças mínimas e reversíveis.
- Validar com testes antes de propor merges.
