# 주식 이상값 AI 분석 플랫폼 - 아키텍처 & 개발 로드맵

---

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [MSA 디렉토리 구조](#2-msa-디렉토리-구조)
3. [전체 기술 스택](#3-전체-기술-스택)
4. [Phase 1 - FastAPI 백엔드](#phase-1--fastapi-백엔드-완료)
5. [Phase 2 - 프론트엔드 대시보드](#phase-2--프론트엔드-대시보드-완료)
6. [Phase 3 - Kafka 파이프라인](#phase-3--kafka-파이프라인-12개월)
7. [Phase 4 - Docker & Kubernetes](#phase-4--docker--kubernetes-23개월)
8. [최종 아키텍처 다이어그램](#8-최종-아키텍처-다이어그램)
9. [DB 스키마 설계](#9-db-스키마-설계)
10. [API 명세](#10-api-명세)

---

## 1. 프로젝트 개요

전 세계 주식 시장에서 **급등/급락 이벤트**를 실시간으로 감지하고,
영문/한국어 뉴스를 바탕으로 **AI가 원인을 분석**해 사용자에게 전달하는 플랫폼.

### 핵심 기능
- 미국/한국 주식 이상값 자동 감지 (퍼센트 변화율 + Z-score)
- 이벤트 유형 자동 분류 (개별 / 섹터 / 시장 전체)
- 영문 + 한국어 뉴스 수집 후 Gemini AI 분석
- 한국어 + 영어 동시 분석 리포트 제공
- 섹터별 글로벌 관심도 트렌드 파악

---

## 2. MSA 디렉토리 구조

각 서비스는 **독립 Docker 이미지**로 빌드 → K8s Pod 분리 기반.

```
project/
├── core/                          # 공유 Python 모듈 (서비스 간 공통)
│   ├── stock_categories.py        # 9개 섹터 정의 + 티커 목록
│   ├── stock_fetcher.py           # yfinance(US) / pykrx(KR) 수집 + 이상값 탐지
│   ├── news_fetcher.py            # NewsAPI + Naver RSS 뉴스 수집
│   └── ai_analyzer.py             # Gemini 2.5 Flash API 래퍼
│
├── services/                      # 마이크로서비스 (각자 독립 이미지)
│   ├── api/                       # ★ FastAPI REST API + WebSocket  [Port 8000]
│   │   ├── Dockerfile             #   build context: 루트 (core/ 접근)
│   │   ├── main.py                #   FastAPI 앱, WebSocket, APScheduler
│   │   ├── db/
│   │   │   ├── connection.py      #   SQLAlchemy async + TimescaleDB
│   │   │   ├── models.py          #   Anomaly, AnalysisResult ORM
│   │   │   └── repository.py      #   DB 쿼리 레포지토리
│   │   ├── routers/
│   │   │   ├── anomalies.py       #   GET /api/v1/anomalies
│   │   │   ├── sectors.py         #   GET /api/v1/sectors/trending
│   │   │   └── jobs.py            #   POST /api/v1/analyze/trigger
│   │   ├── schemas/
│   │   │   └── anomaly.py         #   Pydantic 요청/응답 모델
│   │   └── services/
│   │       └── pipeline.py        #   수집→탐지→저장→AI분석 파이프라인
│   │
│   ├── stock-collector/           # Phase 3: Kafka 'stock.raw.*' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── anomaly-detector/          # Phase 3: Kafka 'anomaly.detected' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── news-fetcher/              # Phase 3: Kafka 'news.fetched' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── ai-analyzer/               # Phase 3: Kafka 'analysis.completed' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   └── notifier/                  # Phase 3: Slack/Email 알림
│       ├── Dockerfile
│       └── main.py
│
├── frontend/                      # ★ Next.js 14 대시보드          [Port 3000]
│   ├── Dockerfile                 #   독립 이미지 (Node 20 멀티스테이지)
│   ├── app/
│   │   ├── page.tsx               #   SSR 초기 데이터 로드
│   │   ├── DashboardClient.tsx    #   클라이언트 레이아웃
│   │   └── components/
│   │       ├── Header.tsx         #   연결 상태 + 수동 분석 트리거
│   │       ├── SectorHeatmap.tsx  #   섹터별 색상 히트맵
│   │       ├── AnomalyList.tsx    #   실시간 이상값 목록
│   │       ├── StockChart.tsx     #   Recharts 이력 차트
│   │       ├── AnalysisPanel.tsx  #   AI 분석 한/영 탭
│   │       └── WsProvider.tsx     #   WebSocket 연결 관리
│   ├── lib/
│   │   ├── api.ts                 #   FastAPI REST 클라이언트
│   │   ├── store.ts               #   Zustand 전역 스토어
│   │   └── websocket.ts           #   WS 자동 재연결
│   └── types/index.ts             #   TypeScript 타입 정의
│
├── cli/                           # CLI 도구 (로컬 실행 / GitHub Actions)
│   └── main.py                    #   python -m cli.main [--demo]
│
├── docker-compose.yml             # 로컬 통합 실행 (Phase 1-2 활성)
├── requirements.txt               # Python 공통 의존성
└── .github/workflows/python.yml   # CI: 평일 09시 자동 실행
```

### Docker 이미지 빌드 방식

| 서비스 | Build Context | Dockerfile 위치 | 이유 |
|--------|-------------|----------------|------|
| `api` | `.` (루트) | `services/api/Dockerfile` | `core/` 공유 모듈 접근 필요 |
| `stock-collector` | `.` (루트) | `services/stock-collector/Dockerfile` | `core/` 접근 필요 |
| `anomaly-detector` | `.` (루트) | `services/anomaly-detector/Dockerfile` | `core/` 접근 필요 |
| `news-fetcher` | `.` (루트) | `services/news-fetcher/Dockerfile` | `core/` 접근 필요 |
| `ai-analyzer` | `.` (루트) | `services/ai-analyzer/Dockerfile` | `core/` 접근 필요 |
| `notifier` | `.` (루트) | `services/notifier/Dockerfile` | 독립 |
| `frontend` | `./frontend` | `frontend/Dockerfile` | Node.js 전용, core 불필요 |

---

## 3. 전체 기술 스택

### Backend
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| API 서버 | **FastAPI** | Python 기반, 비동기 지원, 자동 Swagger 문서 |
| 메시지 큐 | **Apache Kafka** | 대용량 스트림, 서비스 간 완전한 비동기 분리 |
| 시계열 DB | **TimescaleDB** (PostgreSQL 확장) | 주가처럼 시간 기반 데이터 조회에 최적화 |
| 캐시 | **Redis** | API 결과 캐싱, 실시간 알림 큐 |
| ORM | **SQLAlchemy + asyncpg** | 비동기 DB 연결 |

### Frontend
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| 프레임워크 | **Next.js 14** (React) | SSR/SSG 지원, SEO, 빠른 초기 로딩 |
| 상태관리 | **Zustand** | Redux보다 가볍고 간단 |
| 차트 | **Recharts** | React 친화적, 커스터마이징 쉬움 |
| 실시간 | **WebSocket** (native) | 이상값 발생 시 즉시 브라우저 알림 |
| 스타일 | **Tailwind CSS** | 빠른 UI 구성 |

### AI / 데이터
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| AI 분석 | **Gemini 2.5 Flash** | 무료 티어, 한/영 동시 분석 |
| 주가 (미국) | **yfinance** | 무료, 간단한 API |
| 주가 (한국) | **pykrx** | KRX 공식 데이터 |
| 뉴스 (영문) | **NewsAPI + Google RSS** | 무료 티어 존재 |
| 뉴스 (한국) | **네이버 뉴스 RSS** | 무료 |

### Infrastructure
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| 컨테이너 | **Docker** | 환경 일치, 배포 표준 |
| 오케스트레이션 | **Kubernetes (K8s)** | 자동 스케일링, 자가복구, 무중단 배포 |
| CI/CD | **GitHub Actions** | 현재 이미 사용 중 |
| 모니터링 | **Prometheus + Grafana** | K8s 표준 모니터링 스택 |
| 로그 | **ELK Stack** | 분산 로그 수집/분석 |

---

## Phase 1 — FastAPI 백엔드 (완료 ✅)

### 완료된 항목
- [x] FastAPI 서버 (`services/api/`)
- [x] TimescaleDB 연동 (`services/api/db/`)
- [x] REST API 엔드포인트 (`/api/v1/anomalies`, `/sectors`, `/analyze`)
- [x] WebSocket 실시간 이상값 브로드캐스트 (`/ws/live`)
- [x] APScheduler 60분마다 자동 분석
- [x] Swagger UI (`http://localhost:8000/docs`)

---

## Phase 2 — 프론트엔드 대시보드 (완료 ✅)

### 완료된 항목
- [x] Next.js 14 App Router + Tailwind CSS
- [x] 섹터 히트맵 (이상값 빈도 색상 표현)
- [x] 이상값 목록 실시간 업데이트 (WebSocket)
- [x] 종목 클릭 → Recharts 이력 차트
- [x] AI 분석 리포트 한국어/영어 탭 전환
- [x] 수동 분석 트리거 + 진행 상태 표시

---

## Phase 3 — Kafka 파이프라인 (완료 ✅)

### 목표
데이터 수집 → 분석 → 저장 → 알림을 완전히 비동기 파이프라인으로 분리.
`services/api/services/pipeline.py` 안에 순차 실행되던 로직을 각 서비스로 분리.

### Kafka Topic 설계
```
stock.raw.us        미국 주가 배치 데이터 (yfinance) — key: "batch"
stock.raw.kr        한국 주가 배치 데이터 (pykrx)    — key: "batch"
anomaly.detected    이상값 감지 결과                 — key: ticker
news.fetched        뉴스 수집 완료 이벤트             — key: ticker
analysis.completed  AI 분석 완료 결과                — key: ticker
```

### 서비스별 Kafka 흐름
```
[stock-collector]   →  stock.raw.us / stock.raw.kr 에 발행 (1회 실행 후 종료)
[anomaly-detector]  ←  stock.raw.* 구독  →  anomaly.detected 발행
[news-fetcher]      ←  anomaly.detected 구독  →  news.fetched 발행
[ai-analyzer]       ←  news.fetched 구독  →  analysis.completed 발행
[api (db-writer)]   ←  analysis.completed 구독  →  DB 저장 + WS 브로드캐스트
[notifier]          ←  analysis.completed 구독  →  Slack 알림 발송
```

### 메시지 스키마
| Topic | 주요 필드 |
|-------|-----------|
| `stock.raw.*` | `market, timestamp, stocks: {ticker: {date: {OHLCV}}}` |
| `anomaly.detected` | `ticker, date, return_pct, zscore, direction, event_type, sector, ...` |
| `news.fetched` | anomaly 필드 + `news_en[], news_kr[], news_text` |
| `analysis.completed` | news 필드 - news_text + `analysis_ko, analysis_en` |

### 구현 완료 항목
- [x] Kafka + Zookeeper 컨테이너 (`docker-compose.yml` 활성화)
- [x] `stock-collector/main.py` — yfinance/pykrx → Kafka 배치 발행
- [x] `anomaly-detector/main.py` — stock.raw.* 구독 → 탐지+분류 → anomaly.detected
- [x] `news-fetcher/main.py` — anomaly.detected 구독 → 뉴스 수집 → news.fetched
- [x] `ai-analyzer/main.py` — news.fetched 구독 → Gemini 분석 → analysis.completed
- [x] `notifier/main.py` — analysis.completed 구독 → Slack Webhook 발송
- [x] `api/main.py` — analysis.completed 구독 → DB 저장 + WebSocket 브로드캐스트
- [x] `requirements.txt`에 `confluent-kafka>=2.4.0` 추가
- [x] API는 Kafka 없을 때 APScheduler pipeline.py fallback 유지 (하위 호환)

### 장애 격리 특성
- **ai-analyzer 중단** → news-fetcher, anomaly-detector, stock-collector 정상 동작 (메시지 큐에 쌓임)
- **api 중단** → 파이프라인 계속 처리, api 재시작 후 큐에서 이어서 소비
- **notifier 중단** → DB 저장 + WS 브로드캐스트는 api가 독립 처리

---

## Phase 4 — Docker & Kubernetes (2~3개월)

### K8s 리소스 구성
```yaml
# 상태 없는 서비스 (Deployment)
api-server          replicas: 3   # 로드밸런싱
ai-analyzer         replicas: 2   # Gemini API 병렬 처리
anomaly-detector    replicas: 2
frontend            replicas: 2

# 상태 있는 서비스 (StatefulSet)
kafka               replicas: 3   # 브로커 3개 클러스터
timescaledb         replicas: 1   # Primary + 1 Replica
redis               replicas: 1

# 주기적 실행 (CronJob)
stock-collector     schedule: "*/30 * * * 1-5"  # 평일 30분마다

# 자동 스케일링 (HPA)
ai-analyzer         CPU > 70% → Pod 자동 추가 (최대 5개)
api-server          요청 > 100rps → Pod 자동 추가
```

### 무중단 배포 흐름 (GitHub Actions → K8s)
```
코드 push (main)
    │
    ▼
GitHub Actions CI
    ├── 테스트 실행
    ├── Docker 이미지 빌드 (서비스별 독립)
    │   ├── stock-api:$SHA
    │   ├── stock-frontend:$SHA
    │   ├── stock-collector:$SHA
    │   └── ...
    └── Docker Hub에 push
            │
            ▼
    kubectl set image 배포
            │
            ▼
    K8s Rolling Update → 다운타임 0
```

### Phase 4 완료 기준
- [ ] K8s 매니페스트 작성 (`k8s/` 디렉토리: Deployment, Service, Ingress, HPA)
- [ ] GitHub Actions → 서비스별 이미지 자동 빌드 + 푸시
- [ ] Prometheus + Grafana 모니터링 대시보드
- [ ] ELK Stack 로그 수집

---

## 8. 최종 아키텍처 다이어그램

```
                    [ 사용자 브라우저 ]
                           │
                    ┌──────▼──────┐
                    │   Ingress   │  (nginx)
                    │  (K8s)      │
                    └──┬───────┬──┘
                       │       │
              ┌────────▼─┐ ┌───▼────────────┐
              │ Frontend  │ │  API Server    │
              │ Next.js   │ │  FastAPI × 3   │
              │ (Pod × 2) │ │                │
              └───────────┘ └───┬────────┬───┘
                                │  WebSocket
                         ┌──────▼──────────────────────────┐
                         │           Apache Kafka           │
                         │  (StatefulSet × 3 브로커)        │
                         └──┬──────┬──────┬──────┬─────────┘
                    ┌───────┘  ┌───┘  ┌───┘  └──────────┐
              ┌─────▼───┐ ┌────▼──┐ ┌──▼──────┐ ┌───────▼──┐
              │Stock    │ │News   │ │AI       │ │Notifier  │
              │Collector│ │Fetcher│ │Analyzer │ │슬랙/메일  │
              │Detector │ │(Pod×2)│ │(Pod × 2)│ │(Pod × 1) │
              │(Pod × 2)│ └───────┘ └────┬────┘ └──────────┘
              └────┬────┘                │
                   │                     │
              ┌────▼─────────────────────▼──────────────────┐
              │                Databases                     │
              │  ┌──────────────┐  ┌───────┐               │
              │  │ TimescaleDB  │  │ Redis │               │
              │  │ (주가/이상값) │  │(캐시) │               │
              │  └──────────────┘  └───────┘               │
              └──────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Monitoring Stack   │
              │  Prometheus+Grafana │
              └─────────────────────┘
```

---

## 9. DB 스키마 설계

### TimescaleDB (주가 & 이상값)
```sql
CREATE TABLE anomalies (
    id              SERIAL PRIMARY KEY,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    ticker          TEXT        NOT NULL,
    anomaly_date    DATE        NOT NULL,
    return_pct      DECIMAL     NOT NULL,
    zscore          DECIMAL,
    close_price     DECIMAL,
    direction       TEXT,       -- '급등' or '급락'
    event_type      TEXT,       -- 'INDIVIDUAL', 'SECTOR', 'MARKET'
    sector          TEXT,
    sector_peer_count    INT,
    moving_sector_count  INT
);

CREATE TABLE analysis_results (
    id          SERIAL PRIMARY KEY,
    anomaly_id  INT REFERENCES anomalies(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    analysis_ko TEXT,
    analysis_en TEXT,
    news_en     JSONB,
    news_kr     JSONB
);
```

---

## 10. API 명세

```
GET  /api/v1/anomalies
     Query: ?days=7&sector=반도체&event_type=SECTOR&limit=20

GET  /api/v1/anomalies/{ticker}/history
     Query: ?days=30

GET  /api/v1/anomalies/{anomaly_id}/analysis

GET  /api/v1/sectors/trending
     Query: ?days=7
     Response: [{ sector, anomaly_count, avg_return_pct, up_count, down_count, hot_tickers }]

POST /api/v1/analyze/trigger
     Response: { job_id, status: "queued" }

GET  /api/v1/analyze/jobs/{job_id}
     Response: { status, started_at, completed_at, anomaly_count }

WS   /ws/live
     Server → Client: { type: "anomaly", ticker, return_pct, sector, event_type }
```

---

## 개발 우선순위 요약

| 단계 | 상태 | 핵심 가치 |
|------|------|-----------|
| Phase 1 (FastAPI + DB) | ✅ 완료 | 결과가 DB에 쌓이고 API로 조회 가능 |
| Phase 2 (Frontend)     | ✅ 완료 | 시각적 대시보드, 실시간 알림 |
| Phase 3 (Kafka)        | ✅ 완료        | 안정적인 파이프라인, 확장성 확보 |
| Phase 4 (K8s)          | 미착수 | 프로덕션 수준 운영, 자동 스케일링 |
