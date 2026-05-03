# GeoPublish

Plataforma SaaS WebGIS para ingestao, processamento e publicacao de dados
geoespaciais raster/vetor. O fluxo principal gera signed URLs para upload em
GCS, processa arquivos com workers Python/GDAL/GeoPandas, publica camadas no
GeoServer e expoe servicos OGC para QGIS, ArcGIS, WebGIS e clientes externos.

## Ambientes

O projeto opera com dois ambientes:

| Ambiente | Objetivo | Infraestrutura |
| --- | --- | --- |
| DEV | Desenvolvimento e validacao local | Docker Compose |
| PROD | Producao real | Google Cloud |

Nao ha ambiente intermediario no plano atual. O deploy em producao deve ser
manual/controlado.

## Arquitetura DEV

```text
Frontend Next.js
  -> FastAPI
  -> Redis Streams
  -> Worker GDAL/GeoPandas
  -> GCS raw/processed
  -> GeoServer
  -> PostGIS
```

Servicos no Docker Compose:

- `frontend`: Next.js com hot reload em `http://localhost:3000`
- `api`: FastAPI com hot reload em `http://localhost:8000`
- `worker`: consumidor Redis Streams em modo continuo
- `postgres`: PostGIS local
- `redis`: fila local
- `geoserver`: OGC local em `http://localhost:8080/geoserver`

Storage em DEV usa GCS real por padrao, para manter paridade com PROD. MinIO
nao e mais o caminho padrao enquanto o codigo estiver GCS/ADC-first.

## Preparar DEV

1. Autentique o ADC local:

```bash
gcloud auth application-default login
```

2. Crie os buckets de desenvolvimento, ou ajuste `env/.env.dev` para buckets
existentes:

```bash
gcloud storage buckets create gs://geopublish-dev-raw --location=us-central1
gcloud storage buckets create gs://geopublish-dev-processed --location=us-central1
```

3. Suba o stack:

```bash
docker compose up --build
```

4. Acesse:

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- GeoServer: `http://localhost:8080/geoserver`

## Fluxo de Publicacao

```text
1. Usuario seleciona raster/vetor no frontend.
2. API gera signed URL de upload.
3. Browser envia arquivo direto para GCS raw.
4. Frontend confirma upload na API.
5. API publica evento no Redis Stream image:uploaded.
6. Worker processa:
   - raster: GDAL -> COG em EPSG:3857
   - vetor: GeoPandas -> PostGIS
7. Worker publica evento image:processed.
8. Worker registra camada no GeoServer:
   - raster: WMS / WMTS / WCS
   - vetor: WMS / WFS
9. API retorna URLs OGC ao frontend/cliente.
```

## PROD

Componentes esperados em producao:

- Frontend no Cloud Run
- API FastAPI no Cloud Run
- Worker em Cloud Run Service para fila continua
- Worker em Cloud Run Job para execucao sob demanda
- Cloud SQL PostgreSQL/PostGIS
- GCS com bucket raw privado e processed para COGs
- Redis gerenciado/externo
- GeoServer dedicado
- Secret Manager para segredos
- Artifact Registry para imagens Docker

## Deploy PROD

O pipeline fica em `infra/cloudbuild/prod.yaml` e deve ser executado somente
quando o deploy em producao for ordenado:

```bash
gcloud builds submit --config infra/cloudbuild/prod.yaml \
  --substitutions=_REGION=us-central1,_REPOSITORY=geopublish
```

O pipeline:

1. Builda API, worker e frontend.
2. Publica imagens no Artifact Registry com tag `$SHORT_SHA`.
3. Atualiza Cloud Run API.
4. Atualiza Cloud Run worker service.
5. Atualiza Cloud Run worker job.
6. Atualiza Cloud Run frontend.

Configuracoes sensiveis nao devem estar no pipeline. Use Secret Manager e
variaveis ja configuradas nos servicos Cloud Run.

## Estrutura

```text
/api        FastAPI, modelos, routers e servicos
/worker     GDAL/GeoPandas, Redis consumers e publicacao GeoServer
/frontend   Next.js
/env        exemplos de configuracao DEV/PROD
/infra      pipeline e infraestrutura cloud
/geoserver  scripts auxiliares
/tests      testes automatizados
```

## Testes

```bash
pytest
```

Para o frontend:

```bash
cd frontend
npm ci
npm run build
```
