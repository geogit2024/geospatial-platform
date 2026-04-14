# Documento Técnico de Arquitetura — GeoPublish

**Versão:** 1.0  
**Data:** Abril / 2026  
**Projeto:** MVP Uploader Solution — Plataforma de Publicação de Imagens Geoespaciais

---

## 1. Visão Geral

O GeoPublish é uma plataforma web para ingestão, processamento e publicação de imagens raster geoespaciais como serviços OGC (WMS, WMTS, WCS). O sistema recebe arquivos GeoTIFF (e formatos afins), normaliza a projeção para EPSG:3857 (Web Mercator), gera Cloud Optimized GeoTIFF (COG) e publica automaticamente no GeoServer, tornando a camada acessível via WMS/WMTS/WCS em SIGs como ArcGIS Online e QGIS.

---

## 2. Diagrama de Arquitetura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CLIENTE / BROWSER                              │
│                          Next.js 14 (Frontend)                           │
│              Upload · Dashboard · Mapa · URLs de Serviço                 │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ HTTPS
                             │
┌────────────────────────────▼─────────────────────────────────────────────┐
│                         FastAPI (API)                                     │
│                  REST · PostgreSQL · MinIO · Redis                        │
│                                                                            │
│  POST /api/upload/signed-url  →  Gera URL presignada para upload direto  │
│  POST /api/upload/confirm     →  Enfileira evento no Redis Stream         │
│  GET  /api/images/            →  Lista imagens e status                   │
│  GET  /api/services/{id}/ogc  →  Retorna URLs WMS/WMTS/WCS               │
│  DELETE /api/images/{id}      →  Remove imagem + camada GeoServer         │
└──────────┬────────────────────────────────────────────────┬──────────────┘
           │                                                │
    Upload direto                               Redis Stream
    (XHR + progresso)                          image:uploaded
           │                                                │
┌──────────▼──────────┐                  ┌─────────────────▼────────────────┐
│   MinIO (S3)         │                  │         GDAL Worker               │
│                      │                  │                                    │
│  raw-images/         │◄─── download ────│  1. Download raw raster            │
│  processed-images/   │──── upload COG ─►│  2. Audit (CRS, bbox, NoData)     │
│  (public-read)       │                  │  3. Normalize → EPSG:3857 → COG   │
└──────────────────────┘                  │  4. Extrai metadados               │
                                          │  5. Upload COG                     │
                                          │  6. Publica evento image:processed │
                                          │                                    │
                                          │  ── Redis Stream image:processed ──│
                                          │                                    │
                                          │  7. Cria CoverageStore GeoServer   │
                                          │  8. Cria layer (SRS + bbox)        │
                                          │  9. Configura GeoWebCache          │
                                          │  10. Valida WMS GetMap             │
                                          │  11. Atualiza DB: status=published │
                                          └─────────────────┬────────────────-─┘
                                                            │ REST API
                                          ┌─────────────────▼────────────────┐
                                          │          GeoServer 2.25+          │
                                          │  workspace: geoimages             │
                                          │  Lê COG via HTTP Range requests   │
                                          │  WMS · WMTS · WCS                 │
                                          └──────────────────────────────────┘
```

---

## 3. Stack Tecnológica

| Camada | Tecnologia | Versão |
|---|---|---|
| Frontend | Next.js + React | 14.2 / 18 |
| Estilo | TailwindCSS | 3.4 |
| Mapa interativo | Leaflet + react-leaflet | 1.9 / 4.2 |
| API | FastAPI + Uvicorn | 0.111 / 0.29 |
| ORM / DB | SQLAlchemy asyncio + asyncpg | 2.0 / 0.29 |
| Banco de dados | PostgreSQL | 16 |
| Fila de eventos | Redis Streams | 7 |
| Armazenamento | MinIO (S3-compatible) | RELEASE.2024 |
| Processamento raster | GDAL CLI (subprocess) | 3.8.4 |
| Serviços OGC | GeoServer | 2.25 |
| Containerização | Docker + Docker Compose | — |
| Deploy | Railway | — |

---

## 4. Serviços e Responsabilidades

### 4.1 Frontend (Next.js 14)

Aplicação React em modo standalone com três páginas principais:

| Página | Rota | Função |
|---|---|---|
| Upload | `/upload` | Formulário de seleção e envio de arquivo diretamente para o MinIO via URL presignada com progresso em tempo real |
| Dashboard | `/dashboard` | Lista de imagens com status, painel de metadados (ID, CRS, BBox, URLs OGC, URL do serviço WMS copiável) |
| Mapa | `/map` | Visualizador Leaflet com overlay WMS da camada publicada |

**Proxy de API** — `src/app/api/[...path]/route.ts`  
Todas as requisições `/api/*` do navegador passam por um proxy Next.js no servidor, que repassa para o backend usando a variável de ambiente `API_URL` lida em tempo de execução (não em build time). Isso permite alterar a URL do backend sem reconstruir a imagem.

---

### 4.2 API (FastAPI)

Responsável pela orquestração: autenticação de uploads, persistência no banco de dados, publicação de eventos e exposição dos metadados.

#### Endpoints principais

```
POST /api/upload/signed-url
  Cria registro Image (status=UPLOADING)
  Gera presigned PUT URL (TTL 1h) para upload direto ao MinIO
  Retorna: image_id, upload_url, raw_key

POST /api/upload/confirm
  Atualiza status → UPLOADED
  Publica evento no Redis Stream image:uploaded
  Retorna: {"status": "uploaded", "message": "Processing queued"}

GET  /api/images/
  Lista imagens com filtro por status e paginação

GET  /api/images/{id}
  Retorna imagem com todos os campos (CRS, bbox, URLs OGC)

GET  /api/services/{id}/ogc
  Retorna WMS/WMTS/WCS GetCapabilities e GetMap de exemplo

DELETE /api/images/{id}
  Remove registro do banco e coverageStore do GeoServer
```

#### Modelo de dados — tabela `images`

| Campo | Tipo | Descrição |
|---|---|---|
| id | UUID | Chave primária (auto-gerado) |
| filename | VARCHAR(512) | Nome original do arquivo |
| original_key | TEXT | Caminho S3 do arquivo bruto |
| processed_key | TEXT | Caminho S3 do COG gerado |
| status | ENUM | Fluxo de status (ver §6) |
| error_message | TEXT | Detalhe de falha |
| crs | TEXT | CRS nativo do COG (ex: EPSG:3857) |
| bbox_minx/miny/maxx/maxy | FLOAT | Bounding box em WGS84 graus |
| layer_name | TEXT | Nome da camada no GeoServer (workspace:layer) |
| wms_url | TEXT | URL base do serviço WMS |
| wmts_url | TEXT | URL base do serviço WMTS |
| wcs_url | TEXT | URL base do serviço WCS |
| created_at | TIMESTAMP | Data de criação |
| updated_at | TIMESTAMP | Última atualização |

---

### 4.3 Worker GDAL

Processo Python assíncrono que consome dois Redis Streams em paralelo.

#### Estágio 1 — `process_uploaded_image`
Acionado pelo stream `image:uploaded`.

```
1. Download do arquivo bruto do MinIO (streaming via get_object)
2. Auditoria: CRS presente? NoData definido? Georeferenciamento válido?
3. Normalização GDAL:
     a. gdal_translate -a_srs EPSG:4326   (atribui CRS se ausente)
     b. gdalwarp -t_srs EPSG:3857         (reprojeta para Web Mercator)
     c. gdal_translate -of COG            (gera Cloud Optimized GeoTIFF)
        COMPRESS=DEFLATE, PREDICTOR=2
        BLOCKXSIZE=BLOCKYSIZE=512
        OVERVIEW_RESAMPLING=AVERAGE
4. Extração de metadados (CRS, bbox nativa EPSG:3857, bbox WGS84)
5. Upload do COG para MinIO:processed-images
6. Publica evento no stream image:processed com:
     - gs_data_path  (URL HTTPS pública do COG)
     - native_crs    (EPSG:3857)
     - native_bbox   (metros EPSG:3857, JSON)
```

#### Estágio 2 — `publish_processed_image`
Acionado pelo stream `image:processed`.

```
1. Upsert GeoServer CoverageStore
     - Tipo: GeoTIFF
     - URL: HTTPS pública do COG no MinIO (HTTP Range requests)
2. Upsert Coverage (layer)
     - SRS: native CRS + EPSG:4326 + EPSG:3857
     - projectionPolicy: REPROJECT_TO_DECLARED
     - nativeBoundingBox: metros EPSG:3857 (extent exata)
     - latLonBoundingBox: graus WGS84 (obrigatório para ArcGIS Online)
3. Configura GeoWebCache (gridsets EPSG:3857 + EPSG:4326, PNG + JPEG)
4. Valida WMS: GetMap 1.3.0 256×256 PNG via URL interna do GeoServer
     - Falha → rollback: remove coverageStore, status=error
     - Sucesso → atualiza DB: status=published + layer_name + URLs OGC
```

#### Pipeline GDAL — `worker/pipeline/__init__.py`

Todas as operações usam ferramentas CLI via subprocess. Não são utilizados bindings Python do GDAL (exceto para transformação de CRS como fallback).

| Função | Ferramenta CLI | Descrição |
|---|---|---|
| `audit_raster()` | `gdalinfo -json` | Inspeciona CRS, NoData, bbox, dimensões |
| `normalize_raster()` | `gdalwarp` + `gdal_translate` | Reprojeção + geração COG |
| `get_raster_metadata()` | `gdalinfo -json` | Extrai CRS e bbox do COG final |
| `build_overviews()` | `gdaladdo` | Pirâmides de resolução |

**Extração de EPSG:** O WKT de um PROJCRS contém múltiplas entradas `ID["EPSG",...]` — a última corresponde ao CRS projetado externo (ex: EPSG:3857). O sistema usa `re.findall()[-1]` para garantir a extração correta.

---

### 4.4 Armazenamento — MinIO

Dois buckets S3:

| Bucket | Política | Uso |
|---|---|---|
| `raw-images` | privado | Arquivos originais enviados pelo cliente |
| `processed-images` | public-read | COGs gerados — acessíveis via URL HTTPS simples pelo GeoServer |

O bucket `processed-images` tem política `public-read` para que o GeoServer acesse os COGs via HTTP Range requests sem necessidade de URL presignada (que teria TTL limitado).

---

### 4.5 GeoServer

Servidor OGC que expõe as camadas publicadas.

| Recurso | Valor |
|---|---|
| Workspace | `geoimages` |
| Nome do layer | `img_{uuid_com_underscores}` |
| Tipo de store | GeoTIFF (COG via HTTPS) |
| SRS anunciados | EPSG:3857, EPSG:4326 + CRS nativo |
| Projection Policy | REPROJECT_TO_DECLARED |
| GeoWebCache | Gridsets EPSG:3857 + EPSG:4326 + GoogleMapsCompatible |

**Persistência:** O container GeoServer no Railway não possui volume persistente. A cada reinicialização do worker, a função `sync_geoserver_on_startup()` reconcilia todas as imagens com status `published` no banco de dados, recriando os layers automaticamente.

---

## 5. Fluxo Completo de uma Requisição

```
Usuário seleciona arquivo GeoTIFF no frontend
        │
        ▼
POST /api/upload/signed-url
  → Cria registro Image (status=UPLOADING)
  → Retorna presigned PUT URL (MinIO)
        │
        ▼
XHR PUT direto para MinIO (upload com progresso)
        │
        ▼
POST /api/upload/confirm
  → status=UPLOADED
  → Publica evento Redis: image:uploaded
        │
        ▼
Worker consome image:uploaded
  → Download → Auditoria → Normalização GDAL → Upload COG
  → status=processing → status=processed
  → Publica evento Redis: image:processed
        │
        ▼
Worker consome image:processed
  → GeoServer: CoverageStore + Coverage + GWC
  → Valida WMS GetMap (interno)
  → status=published + wms_url + wmts_url + wcs_url
        │
        ▼
Dashboard atualiza via polling (5s)
  → Exibe metadados, URLs OGC, campo "URL do serviço WMS" copiável
        │
        ▼
Usuário copia URL WMS e adiciona no ArcGIS Online / QGIS
```

---

## 6. Fluxo de Status da Imagem

```
pending → uploading → uploaded → processing → processed → publishing → published
                                                                  └──► error
```

| Status | Gatilho |
|---|---|
| `pending` | Registro criado |
| `uploading` | URL presignada gerada |
| `uploaded` | Upload confirmado pelo cliente |
| `processing` | Worker iniciou o pipeline GDAL |
| `processed` | COG gerado e enviado ao MinIO |
| `publishing` | Worker iniciou publicação no GeoServer |
| `published` | Layer ativo no GeoServer, WMS validado |
| `error` | Falha em qualquer etapa (mensagem detalhada no campo `error_message`) |

---

## 7. Comunicação entre Serviços

### Redis Streams

```
Stream: image:uploaded
  Campos: image_id, raw_key, filename
  Produtor: API (POST /upload/confirm)
  Consumidor: Worker (xreadgroup, consumer group: workers)

Stream: image:processed
  Campos: image_id, processed_key, gs_data_path,
          filename, native_crs, native_bbox (JSON)
  Produtor: Worker (Stage 1)
  Consumidor: Worker (Stage 2)
```

O uso de `xreadgroup` com `block=5000ms` garante que múltiplas réplicas do worker não processem a mesma mensagem. A confirmação (`xack`) ocorre apenas após o processamento bem-sucedido.

---

## 8. Configuração e Variáveis de Ambiente

| Variável | Serviço | Descrição |
|---|---|---|
| `DATABASE_URL` | API, Worker | PostgreSQL asyncpg |
| `REDIS_URL` | API, Worker | Redis connection string |
| `STORAGE_ENDPOINT` | API, Worker | URL interna do MinIO |
| `STORAGE_PUBLIC_URL` | Worker | URL HTTPS pública (para GeoServer e presigned URLs) |
| `STORAGE_ACCESS_KEY` | API, Worker | Credencial MinIO |
| `STORAGE_SECRET_KEY` | API, Worker | Credencial MinIO |
| `GEOSERVER_URL` | Worker | URL interna REST (ex: http://geoserver:8080/geoserver) |
| `GEOSERVER_PUBLIC_URL` | Worker | URL HTTPS pública (OGC URLs retornadas ao cliente) |
| `GEOSERVER_ADMIN_USER` | Worker | Usuário admin GeoServer |
| `GEOSERVER_ADMIN_PASSWORD` | Worker | Senha admin GeoServer |
| `GEOSERVER_WORKSPACE` | Worker | Nome do workspace (geoimages) |
| `API_URL` | Frontend | URL do backend (lida em runtime, não em build time) |

---

## 9. Deploy — Railway

Cada serviço é implantado como um serviço independente no Railway:

| Serviço | Contexto de Build | Dockerfile |
|---|---|---|
| API | `/` (raiz) | `Dockerfile.api` |
| Frontend | `frontend/` | `frontend/Dockerfile` |
| Worker | `worker/` | `worker/Dockerfile` |
| GeoServer | Railway Docker image | `kartoza/geoserver` |
| MinIO | `minio/` | `minio/Dockerfile` |

**Comandos de deploy:**
```bash
# API
railway up --service api

# Frontend
cd frontend && railway up --service frontend

# Worker
cd worker && railway up --service worker
```

**Health checks:**
- API: `GET /health`
- Frontend: `GET /dashboard`
- Worker: ping Redis via Python

---

## 10. Decisões Arquiteturais Relevantes

### Upload direto ao MinIO (presigned URL)
O cliente faz PUT diretamente ao MinIO, evitando que a API seja gargalo para arquivos grandes. A API apenas gera a URL presignada e confirma o upload.

### GDAL via subprocess (sem bindings Python)
O pipeline usa ferramentas CLI (`gdalwarp`, `gdal_translate`, `gdalinfo`, `gdaladdo`) via subprocess. Isso torna o código mais portável e evita problemas de incompatibilidade de versão entre bindings e instalação do GDAL.

### COG público (sem presigned URL para GeoServer)
O bucket `processed-images` é público. O GeoServer acessa o COG via URL HTTPS simples com HTTP Range requests (nativo no GeoServer 2.21+). Presigned URLs expirariam (máximo 7 dias no MinIO), quebrando as camadas.

### Reconciliação no startup
O GeoServer no Railway não persiste configuração entre reinicializações. O worker executa `sync_geoserver_on_startup()` a cada inicialização, recriando todos os layers a partir do banco de dados PostgreSQL.

### Proxy de API no frontend em runtime
A URL do backend (`API_URL`) é lida em tempo de execução pelo proxy Next.js (`/api/[...path]/route.ts`), não durante o build. Isso permite redirecionar o frontend para qualquer ambiente sem rebuild da imagem Docker.

### Detecção de EPSG em WKT
WKT de CRS projetado (PROJCRS) contém múltiplas entradas `ID["EPSG",...]` — a primeira corresponde ao CRS geográfico base (EPSG:4326) e a última ao CRS projetado (ex: EPSG:3857). O sistema usa `re.findall()[-1]` para extrair o código correto.

---

## 11. Estrutura de Diretórios

```
UPLOADER-SOLUTION/
├── api/                        # Serviço FastAPI
│   ├── main.py                 # App, lifespan, routers
│   ├── config.py               # Settings (pydantic)
│   ├── database.py             # SQLAlchemy async
│   ├── models/image.py         # ORM + enums
│   ├── routers/upload.py       # Signed URL + confirm
│   ├── routers/images.py       # CRUD
│   ├── routers/services.py     # OGC endpoints
│   └── services/storage.py     # MinIO client
│
├── worker/                     # Serviço de processamento
│   ├── worker.py               # Event loop + pipeline stages
│   ├── config.py               # Settings
│   ├── storage_client.py       # S3 download/upload
│   ├── geoserver_client.py     # GeoServer REST API
│   └── pipeline/
│       ├── __init__.py         # audit, normalize, metadata (GDAL CLI)
│       ├── cog.py              # gdal_translate COG
│       ├── reproject.py        # gdalwarp
│       └── pyramids.py         # gdaladdo
│
├── frontend/                   # Aplicação Next.js
│   └── src/
│       ├── app/
│       │   ├── api/[...path]/  # Proxy runtime → backend
│       │   ├── dashboard/      # Lista + detalhes de imagens
│       │   ├── upload/         # Formulário de upload
│       │   └── map/            # Mapa Leaflet
│       ├── components/         # Sidebar, StatusBadge
│       └── lib/
│           ├── api.ts          # Cliente TypeScript
│           └── utils.ts        # Helpers
│
├── docker-compose.yml          # Stack local completo
├── Dockerfile.api              # Build API
├── Dockerfile.worker           # Build Worker (base GDAL)
└── .env.example                # Variáveis de ambiente
```

---

*Documento gerado em Abril/2026 — RK Sistemas*
