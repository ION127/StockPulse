# StockPulse — 데이터 흐름도 (DFD)

> 작성일: 2026-03-19
> 프로젝트: StockPulse (주식 이상값 AI 분석 플랫폼)

---

## Level 0 — 컨텍스트 다이어그램

시스템 전체를 하나의 프로세스로 보는 최상위 뷰입니다.

```
  ┌──────────────────┐
  │  yfinance API    │  미국 주식 1분봉 OHLCV
  └────────┬─────────┘
           │
  ┌────────┴─────────┐
  │  KIS WebSocket   │  한국 주식 실시간 시세
  └────────┬─────────┘
           │
  ┌────────┴─────────┐
  │ NewsAPI          │  영문 뉴스
  │ Naver RSS        │  한국 뉴스
  └────────┬─────────┘
           │
  ┌────────┴──────────┐
  │ Gemini 2.5 Flash  │  AI 분석 API
  └────────┬──────────┘
           │
           ▼
  ┌─────────────────────────────────┐
  │                                 │
  │         StockPulse 시스템       │◄──► 사용자 (웹 브라우저)
  │                                 │
  └─────────────────────────────────┘
           │
           ▼
  ┌──────────────────┐
  │  Slack 채널      │  이상값 알림 수신
  └──────────────────┘
```

---

## Level 1 — 주요 프로세스 흐름

8개 마이크로서비스 간 데이터 이동을 나타냅니다.

```
 외부 데이터 소스
 ─────────────────────────────────────────────────────────────────────

 [yfinance API]                              [KIS WebSocket]
      │ OHLCV 1분봉 (미국)                         │ 실시간 시세 (한국)
      ▼                                            ▼
 ┌──────────────────┐                   ┌──────────────────┐
 │  1. stock-       │                   │  2. kis-         │
 │     collector    │                   │     bridge       │
 │  yfinance 60s    │                   │  KIS WebSocket   │
 │  폴링 루프       │                   │  클라이언트      │
 └────────┬─────────┘                   └────────┬─────────┘
          │ stock.raw.us (Kafka)                  │ stock.raw.kr (Kafka)
          └──────────────────┬────────────────────┘
                             ▼
                   ┌──────────────────────────┐
                   │  3. anomaly-detector     │
                   │  · Z-score 계산          │
                   │  · 변화율 임계값 검사     │
                   │    US: ±1.5% / KR: ±4%  │
                   │  · 이벤트 분류           │
                   │    INDIVIDUAL / SECTOR   │
                   │    / MARKET              │
                   └──────────────┬───────────┘
                                  │ anomaly.detected (Kafka)
                                  │ { ticker, return_pct, sector,
                                  │   event_type, bar_timestamp }
                                  ▼
                   ┌──────────────────────────┐
                   │  4. news-fetcher         │
                   │  · NewsAPI → 영문 뉴스   │
                   │  · Naver RSS → 한국 뉴스 │
                   │  · 섹터 키워드 필터링    │
                   │  · max 5건 / 3일 이내    │
                   └──────────────┬───────────┘
                                  │ news.fetched (Kafka)
                                  │ { anomaly + news_en[] + news_kr[] }
                                  ▼
                   ┌──────────────────────────┐
                   │  5. ai-analyzer          │
                   │  · Gemini 2.5 Flash      │
                   │  · 한국어 분석 생성      │
                   │  · 영어 분석 생성        │
                   │  · Rate limit 15회/분    │
                   │  · 429 → 지수 백오프     │
                   └──────────────┬───────────┘
                                  │ analysis.completed (Kafka)
                                  │ { anomaly + news + analysis_ko
                                  │   + analysis_en }
                    ┌─────────────┴──────────────────────┐
                    ▼                                     ▼
       ┌─────────────────────────┐          ┌──────────────────────┐
       │  6. api (FastAPI)       │          │  7. notifier         │
       │  · Kafka 컨슈머         │          │  · Slack 웹훅 전송   │
       │  · TimescaleDB 저장     │          │  · 섹터/타입 필터링  │
       │  · WebSocket 브로드캐스트│          └──────────┬───────────┘
       │  · REST API 제공        │                     │
       └──────────┬──────────────┘                     ▼
                  │                          [Slack 채널]
       ┌──────────┴──────────┐
       │                     │
       ▼                     ▼
 ┌───────────────┐    ┌───────────────────────────────────┐
 │ TimescaleDB   │    │  8. frontend (Next.js 14)         │
 │               │    │                                   │
 │ anomalies     │◄──►│  SSR  GET /api/v1/anomalies       │
 │ (hypertable)  │    │       GET /api/v1/sectors/trending│
 │               │    │                                   │
 │ analysis_     │    │  WS   /ws/live                    │
 │ results       │    │       실시간 이상값 수신           │
 │               │    │                                   │
 └───────────────┘    │  REST GET /{ticker}/history       │
                      │       GET /{anomaly_id}/analysis  │
                      │                                   │
                      │  컴포넌트                         │
                      │  ├─ AnomalyList   기업명 표시     │
                      │  ├─ SectorHeatmap 섹터 히트맵     │
                      │  ├─ StockChart    이력 차트       │
                      │  └─ AnalysisPanel AI 분석 결과   │
                      └───────────────────────────────────┘
                                        ▲
                               [사용자 브라우저]
```

---

## Level 2 — Kafka 토픽 데이터 구조

각 Kafka 토픽에서 흐르는 데이터의 구조입니다.

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  stock.raw.us / stock.raw.kr                                   │
 ├─────────────────────────────────────────────────────────────────┤
 │  {                                                              │
 │    "market": "US" | "KR",                                      │
 │    "timestamp": "2024-01-15 09:30:00",                         │
 │    "stocks": {                                                  │
 │      "NVDA": {                                                  │
 │        "2024-01-15 09:30:00": {                                 │
 │          "open": 500.0, "high": 505.0,                         │
 │          "low": 498.0,  "close": 503.0, "volume": 1000000      │
 │        }                                                        │
 │      }                                                          │
 │    }                                                            │
 │  }                                                              │
 └─────────────────────────────────────────────────────────────────┘
                          │
                          ▼ anomaly-detector 처리
 ┌─────────────────────────────────────────────────────────────────┐
 │  anomaly.detected                                               │
 ├─────────────────────────────────────────────────────────────────┤
 │  {                                                              │
 │    "ticker": "NVDA",                                            │
 │    "bar_timestamp": "2024-01-15 09:30:00",                     │
 │    "return_pct": 3.45,                                         │
 │    "zscore": 4.2,                                              │
 │    "close_price": 503.0,                                       │
 │    "volume": 1000000,                                          │
 │    "direction": "급등",                                         │
 │    "is_etf": false,                                            │
 │    "event_type": "INDIVIDUAL",                                 │
 │    "sector": "반도체 (Semiconductor)",                          │
 │    "sector_peer_count": 2,                                     │
 │    "moving_sector_count": 1                                    │
 │  }                                                              │
 └─────────────────────────────────────────────────────────────────┘
                          │
                          ▼ news-fetcher 처리
 ┌─────────────────────────────────────────────────────────────────┐
 │  news.fetched                                                   │
 ├─────────────────────────────────────────────────────────────────┤
 │  {                                                              │
 │    ...anomaly,                                                  │
 │    "news_en": [                                                 │
 │      { "title": "...", "url": "...",                            │
 │        "source": "...", "published_at": "..." }                │
 │    ],                                                           │
 │    "news_kr": [ ... ]                                          │
 │  }                                                              │
 └─────────────────────────────────────────────────────────────────┘
                          │
                          ▼ ai-analyzer 처리
 ┌─────────────────────────────────────────────────────────────────┐
 │  analysis.completed                                             │
 ├─────────────────────────────────────────────────────────────────┤
 │  {                                                              │
 │    ...news_fetched,                                             │
 │    "analysis_ko": "NVIDIA가 급등한 이유는...",                   │
 │    "analysis_en": "NVIDIA surged because..."                   │
 │  }                                                              │
 └─────────────────────────────────────────────────────────────────┘
```

---

## Level 2 — 데이터베이스 스키마

```
 TimescaleDB (PostgreSQL 15)
 ─────────────────────────────────────────────────────────────────

 ┌──────────────────────────────────────────────────────────────┐
 │  anomalies  (Hypertable — anomaly_date 기준 파티셔닝)         │
 ├──────────────────────┬───────────────────────────────────────┤
 │  id                  │  SERIAL PRIMARY KEY                   │
 │  detected_at         │  TIMESTAMPTZ  DEFAULT NOW()           │
 │  ticker              │  VARCHAR(20)  INDEX                   │
 │  anomaly_date        │  DATE         INDEX (파티션 키)       │
 │  bar_timestamp       │  VARCHAR(30)                          │
 │  return_pct          │  FLOAT        NOT NULL                │
 │  zscore              │  FLOAT        NULLABLE                │
 │  close_price         │  FLOAT        NULLABLE                │
 │  volume              │  BIGINT       NULLABLE                │
 │  direction           │  VARCHAR(10)  '급등' | '급락'         │
 │  is_etf              │  BOOLEAN      DEFAULT FALSE           │
 │  event_type          │  VARCHAR(20)  INDEX                   │
 │  sector              │  VARCHAR(100) INDEX                   │
 │  sector_peer_count   │  INT                                  │
 │  moving_sector_count │  INT                                  │
 └──────────────────────┴───────────────────────────────────────┘
                                    │ 1
                                    │
                                    │ N (1:1 실제)
 ┌──────────────────────────────────▼───────────────────────────┐
 │  analysis_results                                            │
 ├──────────────────────┬───────────────────────────────────────┤
 │  id                  │  SERIAL PRIMARY KEY                   │
 │  anomaly_id          │  INT  UNIQUE  FK → anomalies.id       │
 │  created_at          │  TIMESTAMPTZ  DEFAULT NOW()           │
 │  analysis_ko         │  TEXT                                 │
 │  analysis_en         │  TEXT                                 │
 │  news_en             │  JSONB  DEFAULT '[]'                  │
 │  news_kr             │  JSONB  DEFAULT '[]'                  │
 └──────────────────────┴───────────────────────────────────────┘
```

---

## Level 2 — API 엔드포인트 데이터 흐름

```
 브라우저                     FastAPI                    TimescaleDB
    │                            │                            │
    │── GET /api/v1/anomalies ──►│                            │
    │   ?days=7&limit=20         │── SELECT anomalies ───────►│
    │                            │   ORDER BY |return_pct|   │
    │◄── AnomalyResponse[] ──────│◄──────────────────────────│
    │                            │                            │
    │── GET /{ticker}/history ──►│                            │
    │   ?days=30                 │── SELECT anomalies ───────►│
    │                            │   WHERE ticker=?           │
    │◄── AnomalyResponse[] ──────│◄──────────────────────────│
    │                            │                            │
    │── GET /{id}/analysis ─────►│                            │
    │                            │── SELECT analysis_results ►│
    │◄── AnalysisResponse ───────│◄──────────────────────────│
    │                            │                            │
    │── GET /sectors/trending ──►│                            │
    │   ?days=7                  │── GROUP BY sector ────────►│
    │                            │   COUNT, AVG, hot_tickers  │
    │◄── SectorTrendItem[] ──────│◄──────────────────────────│
    │                            │                            │
    │── WS /ws/live ────────────►│                            │
    │                            │  Kafka consumer 수신       │
    │◄── { type:"anomaly", ... }─│  analysis.completed        │
    │    (실시간 브로드캐스트)    │                            │
```

---

## 서비스 포트 & 인프라

```
 ┌──────────────────────────────────────────────────────────────┐
 │  인프라 컴포넌트                                              │
 ├────────────────────┬──────────────┬───────────────────────── ┤
 │  서비스             │  포트        │  역할                   │
 ├────────────────────┼──────────────┼───────────────────────── ┤
 │  frontend          │  3000        │  Next.js 대시보드        │
 │  api               │  8000        │  FastAPI REST + WS       │
 │  TimescaleDB       │  5432        │  주 데이터베이스         │
 │  Kafka             │  9092        │  메시지 브로커           │
 │  Zookeeper         │  2181        │  Kafka 코디네이터        │
 │  Redis             │  6379        │  세션/캐시               │
 └────────────────────┴──────────────┴─────────────────────────┘

 Kubernetes 배포
 ┌────────────────────┬──────────────┬───────────────────────── ┐
 │  서비스             │  Replicas    │  비고                   │
 ├────────────────────┼──────────────┼───────────────────────── ┤
 │  frontend          │  2           │  Stateless               │
 │  api               │  1           │  WebSocket 인메모리 제한 │
 │  stock-collector   │  1           │  단일 폴링 루프          │
 │  kis-bridge        │  1           │  단일 WS 연결            │
 │  anomaly-detector  │  1           │  Kafka 컨슈머 그룹       │
 │  news-fetcher      │  1           │  Kafka 컨슈머 그룹       │
 │  ai-analyzer       │  1           │  Rate limit 고려         │
 │  notifier          │  1           │  Slack 웹훅              │
 └────────────────────┴──────────────┴─────────────────────────┘
```

---

## CI/CD 파이프라인 흐름

```
  개발자 Push
      │
      ▼
  GitHub (main 브랜치)
      │
      ▼ .github/workflows/docker-build.yml
  GitHub Actions
      │
      ├─ docker build stock-api:{SHA}
      ├─ docker build stock-frontend:{SHA}
      ├─ docker build stock-collector:{SHA}
      ├─ docker build stock-anomaly-detector:{SHA}
      ├─ ... (8개 서비스)
      │
      ▼ docker push
  Harbor Registry (10.0.2.105)
      │
      ▼ k8s 매니페스트 image 태그 자동 업데이트
  GitHub (k8s/ 디렉토리 커밋)
      │
      ▼ GitOps 감지 (폴링)
  ArgoCD
      │
      ▼ kubectl apply
  Kubernetes 클러스터
```
