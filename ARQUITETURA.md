# Documento Tecnico de Arquitetura - GeoPublish

**Versao:** 2.0  
**Data:** Abril / 2026  
**Projeto:** MVP Uploader Solution - Plataforma SaaS de Publicacao Geoespacial

---

## 1. Visao Geral

O GeoPublish e uma plataforma web para ingestao, processamento, catalogacao e publicacao de dados geoespaciais. O sistema aceita rasters e vetores, envia os arquivos diretamente para storage, processa os ativos em workers Python, publica camadas no GeoServer e expoe servicos OGC para consumo em ArcGIS Online, QGIS, WebGIS e no proprio visualizador da aplicacao.

O estado atual do codigo cobre:

- Rasters: GeoTIFF/TIFF, JP2, IMG e JPG/JPEG georreferenciavel.
- Vetores: Shapefile em ZIP, KML, GeoJSON e JSON geoespacial.
- Publicacao OGC: WMS, WMTS, WCS e WFS.
- Metricas: storage, acessos, custos estimados/configurados e auditoria de estimativas pre-upload.
- Operacao SaaS inicial: tenant padrao, planos, features, pricing por tenant, assinaturas e eventos.
- Deploy atual orientado a GCP/Cloud Run, Google Cloud Storage, Cloud SQL/PostgreSQL, Redis e GeoServer.

---

## 2. Arquitetura Logica

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         Cliente / Browser                              │
│                  Next.js 14 + React 18 + Tailwind                       │
│ Landing · Acesso · Cadastro · Upload · Dashboard · Mapa                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTPS
                               │ /api/* via proxy runtime do Next.js
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              FastAPI                                    │
│ REST · SQLAlchemy async · GCS signed URLs · Redis Streams               │
│                                                                         │
│ Upload: signed-url, confirm, cost-estimate                              │
│ Images: list, detail, retry, delete, download-url                       │
│ Services: OGC discovery + WMS/WFS/WMTS/WCS proxy                        │
│ Metrics: storage, costs, simulation, cost-estimate audit                │
│ Notifications: SMTP invite/admin welcome                                │
└───────────────┬───────────────────────────────┬─────────────────────────┘
                │                               │
        Signed PUT/GET URL              Redis Streams
                │                       image:uploaded / image:processed
                ▼                               ▼
┌─────────────────────────────┐       ┌───────────────────────────────────┐
│ Google Cloud Storage         │       │ Worker Python                     │
│                              │       │ Redis consumer group: workers     │
│ raw bucket                   │       │                                   │
│ processed/public bucket      │       │ Raster: GDAL CLI -> COG           │
│                              │       │ Vector: GeoPandas -> PostGIS      │
└───────────────┬─────────────┘       │ Publish: GeoServer REST           │
                │                     │ Recovery: stale jobs + xautoclaim │
                │                     └──────────────┬────────────────────┘
                │                                    │
                │                                    ▼
                │                     ┌───────────────────────────────────┐
                │                     │ PostgreSQL / PostGIS              │
                │                     │ images, tenants, plans, metrics,  │
                │                     │ layers_metadata, access logs      │
                │                     └──────────────┬────────────────────┘
                │                                    │
                ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              GeoServer                                  │
│ Raster: CoverageStore GeoTIFF apontando para COG publico em GCS         │
│ Vector: Datastore PostGIS + FeatureType                                 │
│ Servicos: WMS, WMTS/GWC, WCS, WFS                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stack Tecnologica

| Camada | Tecnologia | Observacao |
|---|---|---|
| Frontend | Next.js 14.2.35, React 18, TypeScript | App Router, proxy runtime `/api/[...path]` |
| UI | TailwindCSS, lucide-react, Leaflet | Dashboard, upload, mapa e landing |
| API | FastAPI 0.111, Uvicorn, Pydantic Settings | Routers modulares por dominio |
| ORM/DB | SQLAlchemy asyncio, asyncpg | `NullPool` para Cloud Run/scale-to-zero |
| Banco | PostgreSQL + PostGIS | Metadados, tabelas vetoriais, metricas |
| Fila | Redis Streams | Consumer group `workers`, reclaim com `XAUTOCLAIM` |
| Storage | Google Cloud Storage | Signed URLs v4 e ADC; bucket processado publico para COG |
| Raster | GDAL CLI 3.8.4 | `gdalinfo`, `gdalwarp`, `gdal_translate`, `gdaladdo` |
| Vetor | GeoPandas, GeoAlchemy2, psycopg2 | Normalizacao para EPSG:4326 e carga em PostGIS |
| OGC | GeoServer 2.25.x + GeoWebCache | CoverageStore, Datastore PostGIS, WMS/WMTS/WCS/WFS |
| Deploy | Cloud Run / Cloud Run Jobs / Cloud Build | API, frontend e worker job/servico |
| Local legado | Docker Compose + MinIO | Compose ainda descreve MinIO; ver ponto de atencao em §14 |

---

## 4. Componentes

### 4.1 Frontend

Local: `frontend/`

Principais rotas:

| Rota | Funcao |
|---|---|
| `/` | Landing page comercial |
| `/acesso` e `/cadastro` | Fluxos iniciais de acesso/cadastro |
| `/upload` | Upload direto para storage, progresso por XHR e estimativa de custo opcional |
| `/dashboard` | Lista de camadas, detalhes, metadados, URLs OGC, download e metricas |
| `/map` | Visualizador Leaflet com camadas WMS publicadas |
| `/usuarios` e `/onboarding` | Telas auxiliares de operacao SaaS |

O frontend nao chama a API diretamente pelo host final. Ele usa chamadas relativas para `/api/*`; a rota `frontend/src/app/api/[...path]/route.ts` resolve `API_URL` ou `DEV_API_URL` em tempo de execucao e encaminha a requisicao para o backend. Isso permite alterar o backend em Cloud Run sem rebuild da imagem do frontend.

### 4.2 API FastAPI

Local: `api/`

Responsabilidades:

- Gerar signed URLs v4 para upload/download em GCS.
- Persistir registros em PostgreSQL.
- Classificar estrategia de processamento antes do upload.
- Publicar eventos em Redis Streams.
- Acionar opcionalmente Cloud Run Job do worker.
- Expor discovery e proxies OGC.
- Registrar acessos/downloads para metricas.
- Calcular custos e estimativas pre-upload.
- Enviar notificacoes SMTP quando configurado.

Routers ativos:

| Router | Prefixo | Responsabilidade |
|---|---|---|
| `upload.py` | `/api/upload` | Signed URL, confirmacao, estimativa de custo |
| `images.py` | `/api/images` | Lista, detalhe, retry, download-url, delete |
| `services.py` | `/api/services` | OGC discovery e proxies WMS/WFS/WMTS/WCS |
| `metrics.py` | `/api/metrics` | Storage, custos, simulacao e auditoria |
| `notifications.py` | `/api/notifications` | Convite e boas-vindas por e-mail |

### 4.3 Worker

Local: `worker/`

O worker consome dois streams:

- `image:uploaded`: baixa o arquivo bruto e executa o processamento.
- `image:processed`: publica a camada no GeoServer.

Modos de execucao:

- `WORKER_MODE=service`: processo continuo com health server HTTP opcional.
- `WORKER_MODE=job`: processa lotes finitos e encerra por idle/max runtime, adequado para Cloud Run Jobs.

Recursos de resiliencia:

- `xreadgroup` com consumer group `workers`.
- `xautoclaim` para recuperar mensagens pendentes de consumidores mortos.
- Heartbeat por atualizacao de `images.updated_at`.
- Recuperacao de imagens travadas em `processing` ou `publishing`.
- Sincronizacao opcional no startup para republicar camadas `published` no GeoServer.

### 4.4 Storage

O codigo atual de API e worker usa Google Cloud Storage por ADC:

- API: `api/services/storage.py`
- Worker: `worker/storage_client.py`

Buckets:

| Bucket | Uso | Acesso |
|---|---|---|
| `STORAGE_BUCKET_RAW` | Arquivos originais | Privado, upload/download por signed URL |
| `STORAGE_BUCKET_PROCESSED` | COGs e saidas processadas raster | Publico para leitura pelo GeoServer |

O bucket processado precisa permitir leitura publica dos COGs, porque o GeoServer aponta o CoverageStore para uma URL permanente (`https://storage.googleapis.com/...`) e usa HTTP Range requests. Signed URLs com expiracao quebrariam camadas ja publicadas.

### 4.5 PostgreSQL / PostGIS

O banco guarda metadados operacionais e tabelas vetoriais:

- `images`: registro principal do ativo, status, bbox, URLs OGC, estrategia e instrumentacao de processamento.
- `layers_metadata`: espelho de metadados de camadas publicadas.
- `asset_access_logs`: downloads e chamadas OGC amostradas/registradas.
- `tenants`, `plans`, `plan_features`, `tenant_subscriptions`, `subscription_events`.
- `tenant_pricing`, `tenant_usage_daily`.
- `tenant_cost_estimate_config`, `upload_cost_estimate_sessions`.
- Tabelas PostGIS geradas para vetores (`layer_<id>` no schema configurado).

Na inicializacao da API, `init_db()` roda em background, executa `Base.metadata.create_all`, aplica compatibilidade de schema via `ALTER TABLE/CREATE INDEX IF NOT EXISTS`, semeia planos e cria assinatura padrao.

### 4.6 GeoServer

O GeoServer e a camada de publicacao OGC:

- Rasters: CoverageStore GeoTIFF apontando para COG publico em GCS.
- Vetores: Datastore PostGIS por workspace e FeatureType por tabela.
- WMS: usado pelo dashboard, mapa, ArcGIS e QGIS.
- WMTS: via GeoWebCache, com gridsets EPSG:4326, EPSG:3857 e GoogleMapsCompatible para raster.
- WCS: publicado para raster.
- WFS: publicado para vetor.

O sistema tambem oferece proxies por imagem em `/api/services/{image_id}/...-proxy`. Para WMS, o proxy filtra o GetCapabilities para a camada alvo, reescreve URLs internas para endpoints publicos e aplica ajustes de compatibilidade para ArcGIS Online.

---

## 5. Fluxo de Upload e Processamento

```text
1. Usuario seleciona arquivo no frontend.
2. Frontend pode iniciar estimativa de custo pre-upload.
3. Frontend chama POST /api/upload/signed-url.
4. API valida extensao/tamanho, classifica estrategia e cria Image como uploading.
5. API retorna signed PUT URL do GCS.
6. Browser envia bytes diretamente ao storage por XHR.
7. Frontend chama POST /api/upload/confirm.
8. API marca uploaded, publica image:uploaded e, se habilitado, aciona Cloud Run Job.
9. Worker consome image:uploaded.
10. Worker processa raster ou vetor e marca processed.
11. Worker publica image:processed.
12. Worker consome image:processed, publica no GeoServer e valida WMS.
13. Worker marca published e grava URLs/metadados.
14. Dashboard atualiza por polling e exibe servicos OGC.
```

---

## 6. Pipeline Raster

Entrada: `.tif`, `.tiff`, `.geotiff`, `.jp2`, `.img`, `.jpg`, `.jpeg`.

Fluxo em `worker/pipeline/__init__.py`:

1. `audit_raster()` roda `gdalinfo -json` e registra problemas de CRS, NoData e georreferenciamento.
2. `inspect_raster_optimization()` identifica COG existente, EPSG, driver, dimensoes e overviews.
3. Se o arquivo ja for COG no CRS alvo e `RASTER_SKIP_COG_IF_ALREADY_COG=true`, o worker pode evitar normalizacao.
4. Caso contrario, `normalize_raster()`:
   - atribui `EPSG:4326` se nao houver CRS;
   - reprojeta para `RASTER_TARGET_CRS` (padrao `EPSG:3857`);
   - gera COG com DEFLATE, tiles 512x512 e overview resampling AVERAGE.
5. `get_raster_metadata()` extrai CRS e bboxes nativo/WGS84.
6. COG e enviado para `STORAGE_BUCKET_PROCESSED`.
7. `GeoServerClient.publish_cog()` cria/atualiza CoverageStore, Coverage e GWC.
8. Worker valida WMS GetMap interno antes de finalizar como `published`.

Observacoes:

- O pipeline usa GDAL CLI por subprocess, nao bindings Python de GDAL.
- ECW e rejeitado na API porque o driver nao esta disponivel no ambiente de producao.
- JPG/JPEG entra como raster, mas depende de georreferenciamento ou fallback GDAL com `SRC_METHOD=NO_GEOTRANSFORM`.

---

## 7. Pipeline Vetorial

Entrada: `.zip` com Shapefile, `.kml`, `.geojson`, `.json`.

Fluxo em `worker/services/vector_processor.py`:

1. Detecta tipo por extensao.
2. Para Shapefile, valida ZIP e exige sidecars `.shp`, `.shx` e `.dbf`.
3. Le arquivo com GeoPandas.
4. Remove geometrias nulas/vazias.
5. Assume EPSG:4326 quando nao ha CRS.
6. Reprojeta para EPSG:4326 quando necessario.
7. Corrige geometrias de poligono com `buffer(0)`.
8. Normaliza nomes de colunas para identificadores SQL seguros.
9. Converte tipos nao escalares para string.
10. Opcionalmente simplifica geometrias conforme configuracao.
11. Salva em PostGIS com tabela `layer_<uuid_normalizado>`.
12. Cria indice GIST em `geom`.
13. Publica workspace/datastore/featuretype no GeoServer.

Workspaces vetoriais sao derivados do tenant: `build_workspace_name(tenant_id)`, com prefixo `VECTOR_WORKSPACE_PREFIX` (padrao `user`).

---

## 8. Fluxo de Status

```text
pending -> uploading -> uploaded -> processing -> processed -> publishing -> published
                                                        \             \
                                                         \             -> error
                                                          -> error
```

| Status | Responsavel | Significado |
|---|---|---|
| `pending` | Modelo | Estado inicial teorico |
| `uploading` | API | Registro criado e signed URL emitida |
| `uploaded` | API | Upload confirmado e evento enfileirado |
| `processing` | Worker | Processamento raster/vetor iniciado |
| `processed` | Worker | Saida normalizada pronta para publicacao |
| `publishing` | Worker | Publicacao GeoServer em andamento |
| `published` | Worker | Camada ativa e WMS validado |
| `error` | API/Worker | Falha com `error_message` persistido |

---

## 9. Endpoints Principais

### Upload

| Metodo | Rota | Descricao |
|---|---|---|
| `POST` | `/api/upload/signed-url` | Cria imagem, classifica estrategia e retorna signed PUT URL |
| `POST` | `/api/upload/confirm` | Confirma upload, exige estimativa aceita se informada, enfileira processamento |
| `GET` | `/api/upload/cost-estimate/config` | Retorna configuracao efetiva de estimativa |
| `PUT` | `/api/upload/cost-estimate/config` | Atualiza configuracao por tenant |
| `POST` | `/api/upload/cost-estimate/start` | Cria sessao de estimativa e URL temporaria |
| `POST` | `/api/upload/cost-estimate/calculate` | Recalcula estimativa com premissas alteradas |
| `POST` | `/api/upload/cost-estimate/accept` | Aceita estimativa para vincular ao upload |

### Imagens

| Metodo | Rota | Descricao |
|---|---|---|
| `GET` | `/api/images/` | Lista imagens com filtro opcional de status e paginacao |
| `GET` | `/api/images/{image_id}` | Detalhe da imagem |
| `GET` | `/api/images/{image_id}/download-url` | Signed GET URL para raw ou processed |
| `POST` | `/api/images/{image_id}/retry` | Reenfileira imagem em `error` ou `processing` |
| `DELETE` | `/api/images/{image_id}` | Remove GeoServer, storage, PostGIS/layers_metadata e registro |

### Servicos OGC

| Metodo | Rota | Descricao |
|---|---|---|
| `GET` | `/api/services/{image_id}/ogc` | Discovery de WMS/WFS/WMTS/WCS |
| `GET` | `/api/services/{image_id}/wms-proxy` | Proxy WMS por camada |
| `GET` | `/api/services/{image_id}/wfs-proxy` | Proxy WFS por camada |
| `GET` | `/api/services/{image_id}/wmts-proxy` | Proxy WMTS |
| `GET` | `/api/services/{image_id}/wcs-proxy` | Proxy WCS |

### Metricas e notificacoes

| Metodo | Rota | Descricao |
|---|---|---|
| `GET` | `/api/metrics/storage` | Total, distribuicao, crescimento, top arquivos e top acessos |
| `GET` | `/api/metrics/costs` | Custo por janela, configurado ou via BigQuery Billing Export |
| `POST` | `/api/metrics/costs/simulate` | Simula custo incremental |
| `GET` | `/api/metrics/upload-cost-estimates` | Auditoria de sessoes de estimativa |
| `POST` | `/api/metrics/upload-cost-estimates/cleanup` | Remove sessoes expiradas |
| `POST` | `/api/notifications/invite-user` | Envia convite SMTP |
| `POST` | `/api/notifications/admin-welcome` | Envia boas-vindas SMTP |

---

## 10. Modelo de Dados Resumido

### `images`

Campos relevantes:

- Identificacao: `id`, `tenant_id`, `filename`.
- Storage: `original_key`, `processed_key`.
- Status: `status`, `error_message`.
- Espacial: `crs`, `bbox_minx`, `bbox_miny`, `bbox_maxx`, `bbox_maxy`.
- OGC: `layer_name`, `wms_url`, `wfs_url`, `wmts_url`, `wcs_url`.
- Ativo: `asset_kind`, `source_format`, `geometry_type`.
- GeoServer/PostGIS: `workspace`, `datastore`, `postgis_table`.
- Estrategia: `processing_strategy`, `worker_type`, `processing_queue`.
- Flags: `requires_gdal`, `requires_postgis`, `requires_geoserver`.
- Temporizacao: `processing_started_at`, `processing_finished_at`, `processing_duration_seconds`.
- Auditoria: `created_at`, `updated_at`.

### Tabelas SaaS/metricas

| Tabela | Uso |
|---|---|
| `tenants` | Cadastro logico de tenants |
| `plans`, `plan_features` | Planos e features habilitaveis |
| `tenant_subscriptions`, `subscription_events` | Assinatura e historico |
| `tenant_pricing` | Precificacao por tenant |
| `tenant_usage_daily` | Base de uso diario |
| `asset_access_logs` | Downloads e chamadas OGC |
| `tenant_cost_estimate_config` | Premissas de estimativa por tenant |
| `upload_cost_estimate_sessions` | Sessoes de estimativa, aceite e consumo |
| `layers_metadata` | Espelho de publicacao por camada |

---

## 11. Estrategia de Processamento

A API classifica o arquivo no momento do signed URL com `services/processing_strategy.py`:

| Entrada | `asset_kind` | `processing_strategy` | `worker_type` | Fila logica |
|---|---|---|---|---|
| `.tif`, `.tiff`, `.geotiff` | raster | `raster_light` | `raster` | `processing:raster-light` |
| `.jp2`, `.img` | raster | `raster_heavy` | `raster-heavy` | `processing:raster-heavy` |
| `.jpg`, `.jpeg` | raster | `jpeg_georeferenced` | `raster` | `processing:raster-light` |
| `.zip` | vector | `zip_vector` | `vector-heavy` | `processing:vector-heavy` |
| `.kml`, `.geojson`, `.json` | vector | `vector_light` ou `vector_heavy` | `vector`/`vector-heavy` | `processing:vector-light/heavy` |

No codigo atual os streams Redis ainda sao globais (`image:uploaded` e `image:processed`); a fila logica e persistida para instrumentacao/custos e para evolucao futura.

---

## 12. Metricas, Custos e Auditoria

### Storage

`GET /api/metrics/storage` agrega:

- Total de arquivos.
- Tamanho total e tamanho medio.
- Crescimento por janela.
- Distribuicao por tipo.
- Top arquivos por tamanho.
- Top acessados por download, OGC ou ambos.
- Serie temporal de uso.

Os tamanhos sao lidos do GCS quando disponiveis. Os resultados possuem cache em memoria por TTL.

### Custos

`GET /api/metrics/costs` pode usar:

- `BILLING_COST_SOURCE=configured`: custos fixos de env/pricing.
- `BILLING_COST_SOURCE=gcp_billing_export`: tabela BigQuery de export do Billing.

Tambem ha simulacao incremental em `/api/metrics/costs/simulate`.

### Estimativa pre-upload

A estimativa pre-upload e uma simulacao rapida baseada em:

- tipo de ativo;
- extensao;
- tamanho em GB;
- fator de complexidade;
- premissas de storage/processamento/download;
- pricing por tenant ou defaults.

O fluxo cria uma sessao, permite recalculo, exige aceite quando o upload informa `estimate_session_id` e marca a sessao como `consumed` na confirmacao do upload.

---

## 13. Variaveis de Ambiente Principais

| Variavel | Servico | Descricao |
|---|---|---|
| `DATABASE_URL` | API, Worker | PostgreSQL async; Cloud SQL pode usar socket Unix |
| `REDIS_URL` | API, Worker | Redis connection string |
| `REDIS_STREAM_UPLOADED` | API, Worker | Stream de upload confirmado |
| `REDIS_STREAM_PROCESSED` | API, Worker | Stream de saida pronta para publicacao |
| `REDIS_CONSUMER_GROUP` | Worker | Consumer group dos workers |
| `STORAGE_BUCKET_RAW` | API, Worker | Bucket GCS de originais |
| `STORAGE_BUCKET_PROCESSED` | API, Worker | Bucket GCS de saidas processadas |
| `GEOSERVER_URL` | API, Worker | URL interna do GeoServer |
| `GEOSERVER_PUBLIC_URL` | API, Worker | URL publica usada em respostas/URLs OGC |
| `GEOSERVER_ADMIN_USER` | API, Worker | Usuario admin GeoServer |
| `GEOSERVER_ADMIN_PASSWORD` | API, Worker | Senha admin GeoServer |
| `GEOSERVER_WORKSPACE` | API, Worker | Workspace raster padrao |
| `VECTOR_WORKSPACE_PREFIX` | Worker | Prefixo de workspaces vetoriais |
| `VECTOR_DEFAULT_DATASTORE` | API, Worker | Datastore PostGIS padrao |
| `POSTGIS_SCHEMA` | API, Worker | Schema PostGIS |
| `API_URL` / `DEV_API_URL` | Frontend | Backend usado pelo proxy Next.js |
| `CORS_ORIGINS` | API | Origens permitidas |
| `CORS_ORIGIN_REGEX` | API | Regex para ArcGIS/ArcGIS Online |
| `WORKER_MODE` | Worker | `service` ou `job` |
| `WORKER_JOB_TRIGGER_ENABLED` | API | Aciona Cloud Run Job apos enfileirar |
| `WORKER_JOB_*` | API/Worker | Projeto, regiao, nome e lock de trigger |
| `BILLING_COST_SOURCE` | API | `configured` ou `gcp_billing_export` |
| `GCP_BILLING_EXPORT_*` | API | Projeto/tabela BigQuery do billing |
| `SMTP_*` | API | Envio de convites e boas-vindas |
| `UPLOAD_COST_ESTIMATE_*` | API | Feature flag e premissas de estimativa |
| `RASTER_TARGET_CRS` | API, Worker | CRS alvo raster, padrao `EPSG:3857` |

---

## 14. Deploy e Ambientes

### Producao atual esperada

O codigo atual esta alinhado a GCP:

- API em Cloud Run.
- Frontend em Cloud Run.
- Worker como Cloud Run service ou Cloud Run Job.
- GCS para storage.
- Cloud SQL/PostgreSQL com PostGIS.
- Redis gerenciado ou externo.
- GeoServer acessivel internamente pela API/worker e publicamente por URL HTTPS.
- Cloud Build para imagens (`cloudbuild.api.billing.yaml`, `cloudbuild.api.ondemand-worker.yaml`).

### Compose local

`docker-compose.yml` ainda descreve uma pilha local com PostgreSQL, Redis, MinIO, API, worker e GeoServer. Esse arquivo e util como referencia de topologia local, mas ha um ponto importante: os clientes atuais de storage em `api/services/storage.py` e `worker/storage_client.py` estao implementados para Google Cloud Storage com ADC, nao para MinIO/S3.

Para que o compose volte a funcionar integralmente com MinIO, e necessario reintroduzir/abstrair um backend S3-compatible ou ajustar os containers locais para usar GCS/ADC. Enquanto isso nao for feito, a arquitetura executavel principal e GCS/Cloud Run.

---

## 15. Decisoes Arquiteturais

### ADR-001 - Upload direto ao storage

O browser envia arquivos diretamente ao bucket por signed URL. A API nao trafega os bytes, reduzindo custo, memoria e tempo de request para arquivos grandes.

### ADR-002 - Redis Streams como barramento

Redis Streams desacopla API e worker, oferece persistencia basica, consumer groups e recuperacao de mensagens pendentes. O banco continua sendo a fonte de verdade do estado.

### ADR-003 - COG publico para raster processado

Rasters processados ficam como Cloud Optimized GeoTIFF em bucket publico. O GeoServer precisa de URL permanente e suporte a Range requests; signed URLs expiraveis nao sao adequadas para camadas publicadas.

### ADR-004 - PostGIS para vetores

Vetores sao normalizados para EPSG:4326 e salvos em PostGIS. O GeoServer publica FeatureTypes a partir de um Datastore PostGIS, habilitando WMS/WFS e consultas vetoriais.

### ADR-005 - Proxies OGC por imagem

Os endpoints proxy resolvem problemas de HTTPS, URLs internas, CORS e compatibilidade com ArcGIS Online. O WMS proxy tambem filtra capabilities para a camada especifica, evitando que clientes escolham camadas erradas do workspace.

### ADR-006 - Worker em modo servico ou job

O mesmo codigo roda como worker continuo ou como job on-demand. A API pode disparar Cloud Run Job apos confirmar upload, mantendo o Redis como fonte de persistencia quando o trigger falha.

### ADR-007 - DB init tolerante a cold start

A API inicializa schema em background no lifespan para nao bloquear readiness do Cloud Run. O engine usa `NullPool` para evitar conexoes antigas em scale-to-zero.

---

## 16. Estrutura de Diretorios

```text
UPLOADER-SOLUTION/
├── api/
│   ├── main.py                         # FastAPI app, lifespan e routers
│   ├── config.py                       # Settings
│   ├── database.py                     # SQLAlchemy async e schema compatibility
│   ├── models/                         # ORM: images, tenants, plans, metrics
│   ├── routers/                        # Upload, images, services, metrics, notifications
│   └── services/                       # Storage, queue, custos, metrics, email, trigger
│
├── worker/
│   ├── worker.py                       # Consumers, recovery, job/service mode
│   ├── config.py                       # Settings do worker
│   ├── storage_client.py               # GCS download/upload/public URL
│   ├── geoserver_client.py             # Publicacao raster
│   ├── pipeline/                       # GDAL raster pipeline
│   └── services/
│       ├── vector_processor.py         # GeoPandas/PostGIS
│       ├── geoserver_service.py        # Publicacao vetorial
│       └── processing_strategy.py      # Classificacao
│
├── frontend/
│   ├── src/app/                        # App Router: landing, upload, dashboard, mapa
│   ├── src/components/                 # Shell, sidebar, badges e metricas
│   └── src/lib/                        # Cliente API, auth local, utils
│
├── tests/                              # Testes de pipeline, storage, metrics, WMS e custos
├── geoserver/                          # Scripts auxiliares de workspace
├── minio/                              # Config local legado
├── context/                            # Documentacao auxiliar
├── docker-compose.yml                  # Stack local legada/referencia
├── Dockerfile.api
├── Dockerfile.worker
├── cloudbuild.api.billing.yaml
├── cloudbuild.api.ondemand-worker.yaml
├── .env.example
└── ARQUITETURA.md
```

---

## 17. Testes Existentes

Coberturas relevantes em `tests/`:

- Pipeline raster e normalizacao.
- Helpers vetoriais e extensoes de upload.
- Estrategia de processamento.
- Estimativa de custo pre-upload.
- Limpeza de storage.
- Metricas de storage/custos e fallback de billing.
- Eventos de acesso OGC.
- WMS GetCapabilities filtrado e estilo vetorial.

---

## 18. Pontos de Atencao

1. O compose local ainda usa variaveis e servico MinIO, mas os clientes de storage atuais sao GCS-only. Isso deve ser tratado antes de depender do compose para desenvolvimento completo.
2. `tenant_id` ainda e efetivamente padrao em varios fluxos de upload/listagem; a base SaaS existe, mas isolamento completo por usuario/tenant ainda precisa ser consolidado.
3. A classificacao grava filas logicas, mas o roteamento fisico ainda usa dois streams globais.
4. Autenticacao/autorizacao real ainda nao aparece como camada backend forte; o frontend possui associacao local de proprietario para filtros de UI.
5. O startup da API aplica alteracoes de schema diretamente. Para producao madura, migracoes Alembic versionadas devem substituir esse mecanismo.
6. O GeoServer precisa de URL publica HTTPS consistente para uso externo; os proxies API reduzem o impacto, mas WMTS/WCS ainda podem expor URL publica direta conforme configuracao.

---

*Documento atualizado em Abril/2026 com base na leitura do codigo atual do repositorio.*
