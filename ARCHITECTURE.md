# 주식 이상값 AI 분석 플랫폼 - 아키텍처 & 개발 로드맵

---

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [MSA 디렉토리 구조](#2-msa-디렉토리-구조)
3. [전체 기술 스택](#3-전체-기술-스택)
4. [Phase 1 - FastAPI 백엔드](#phase-1--fastapi-백엔드-완료)
5. [Phase 2 - 프론트엔드 대시보드](#phase-2--프론트엔드-대시보드-완료)
6. [Phase 3 - Kafka 파이프라인](#phase-3--kafka-파이프라인-완료)
7. [Phase 4 - Docker & Kubernetes](#phase-4--docker--kubernetes-완료)
8. [Phase 5 - 개인화 서비스 POC](#phase-5--개인화-서비스-poc-진행중)
9. [최종 아키텍처 다이어그램](#9-최종-아키텍처-다이어그램)
10. [DB 스키마 설계](#10-db-스키마-설계)
11. [API 명세](#11-api-명세)
12. [향후 로드맵](#12-향후-로드맵)

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
- **분봉 차트** — 실제 가격선 위에 이상값 발생 위치를 마커로 표시 (1D/3D/5D 선택)
  - 미국: yfinance 1분봉 / 한국 1D: KIS REST API 분봉 / 한국 3D·5D: pykrx 일봉
- **종목 검색** — 기업명/코드로 임의 종목 검색 후 차트 조회
- **기업명 표시** — 티커 코드 대신 기업명으로 종목 식별 (NVDA → NVIDIA, KR:005930 → 삼성전자)
- **관심 종목 (Watchlist)** — ★로 종목 추가, 내 종목만 필터, localStorage 영속
- **포트폴리오 손익 추적** — 수량·평균단가 입력 → KIS/yfinance 현재가로 실시간 손익 계산

---

## 2. MSA 디렉토리 구조

각 서비스는 **독립 Docker 이미지**로 빌드 → K8s Pod 분리 기반.

```
project/
├── core/                          # 공유 Python 모듈 (서비스 간 공통)
│   ├── stock_categories.py        # 10개 섹터 × (ETF 2개 + 시가총액 상위 종목)
│   ├── stock_fetcher.py           # yfinance 1분봉(US) + 이상값 탐지, ETF 인식 이벤트 분류
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
│   │   │   ├── anomalies.py       #   GET /api/v1/anomalies (has_analysis 필드 포함)
│   │   │   ├── sectors.py         #   GET /api/v1/sectors/trending
│   │   │   ├── jobs.py            #   POST /api/v1/analyze/trigger
│   │   │   └── stocks.py          #   GET /api/v1/stocks/{ticker}/candles
│   │   │                          #     US: yfinance 1분봉
│   │   │                          #     KR 1D: KIS REST API 분봉 (stock-kis-secret 필요)
│   │   │                          #     KR 3D/5D: pykrx 일봉
│   │   ├── schemas/
│   │   │   └── anomaly.py         #   Pydantic 요청/응답 모델
│   │   └── services/
│   │       └── pipeline.py        #   수집→탐지→저장→AI분석 파이프라인
│   │
│   ├── stock-collector/           # 미국 1분봉 → Kafka 'stock.raw.us' (60초 루프)
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── kis-bridge/                # 한국 실시간 → Kafka 'stock.raw.kr'
│   │   ├── Dockerfile             #   KIS WebSocket, 1분봉 집계, 40종목×다중연결
│   │   ├── main.py
│   │   └── requirements.txt
│   │
│   ├── anomaly-detector/          # Kafka 'anomaly.detected' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── news-fetcher/              # Kafka 'news.fetched' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── ai-analyzer/               # Kafka 'analysis.completed' 발행
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   └── notifier/                  # Slack/Email 알림
│       ├── Dockerfile
│       └── main.py
│
├── frontend/                      # ★ Next.js 14 대시보드          [Port 3000]
│   ├── Dockerfile
│   ├── app/
│   │   ├── page.tsx               #   SSR 초기 데이터 로드
│   │   ├── DashboardClient.tsx    #   클라이언트 레이아웃 (3열 상단 + 2열 하단)
│   │   └── components/
│   │       ├── Header.tsx         #   연결 상태 + 수동 분석 트리거 + 검색바
│   │       ├── SearchBar.tsx      #   종목 검색 + ★ 관심 종목 토글
│   │       ├── SectorHeatmap.tsx  #   섹터별 색상 히트맵
│   │       ├── AnomalyList.tsx    #   이상값 목록 (★버튼, 내 종목만 필터)
│   │       ├── StockChart.tsx     #   분봉 가격선 + 이상값 마커 (1D/3D/5D)
│   │       ├── AnalysisPanel.tsx  #   AI 분석 한/영 탭 (분석없음 상태 구분)
│   │       ├── PortfolioPanel.tsx #   관심 종목 + 포트폴리오 손익 (실시간 가격)
│   │       └── WsProvider.tsx     #   WebSocket 연결 관리
│   ├── lib/
│   │   ├── api.ts                 #   FastAPI REST 클라이언트
│   │   ├── store.ts               #   Zustand 전역 스토어
│   │   ├── watchlistStore.ts      #   관심 종목 + 포트폴리오 (Zustand persist)
│   │   ├── websocket.ts           #   WS 자동 재연결
│   │   └── tickerNames.ts         #   티커↔기업명 매핑 (KR: 접두사 정규화)
│   └── types/index.ts             #   TypeScript 타입 (has_analysis 필드 포함)
│
├── k8s/                           # Kubernetes 매니페스트
│   ├── api/deployment.yaml        #   stock-kis-secret 포함 (KR 분봉 API용)
│   └── ...
│
├── docker-compose.yml
└── DFD.md                         # 데이터 흐름도
```

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
| 상태관리 | **Zustand** (+ persist 미들웨어) | Redux보다 가볍고 간단, localStorage 영속 |
| 차트 | **Recharts** | React 친화적, 커스터마이징 쉬움 |
| 실시간 | **WebSocket** (native) | 이상값 발생 시 즉시 브라우저 알림 |
| 스타일 | **Tailwind CSS** | 빠른 UI 구성 |

### AI / 데이터
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| AI 분석 | **Gemini 2.5 Flash** | 무료 티어, 한/영 동시 분석 |
| 주가 (미국) | **yfinance 1분봉** | 무료, 1분봉 polling |
| 주가 (한국 실시간) | **KIS WebSocket** | 체결 → 1분봉 집계 |
| 주가 (한국 분봉 조회) | **KIS REST API** | 당일 분봉 차트 (inquire-time-itemchartprice) |
| 주가 (한국 일봉) | **pykrx** | 3D/5D 일봉 조회 |
| 뉴스 (영문) | **NewsAPI + Google RSS** | 무료 티어 존재 |
| 뉴스 (한국) | **네이버 뉴스 RSS** | 무료 |

### Infrastructure
| 역할 | 기술 |
|------|------|
| 컨테이너 | Docker |
| 오케스트레이션 | Kubernetes (K8s) |
| CI | GitHub Actions (self-hosted runner) |
| CD | ArgoCD (GitOps) |
| 이미지 레지스트리 | Harbor (self-hosted) |
| 모니터링 | Prometheus + Grafana |

---

## Phase 1 — FastAPI 백엔드 (완료 ✅)

- [x] FastAPI 서버 (`services/api/`)
- [x] TimescaleDB 연동
- [x] REST API 엔드포인트 (`/api/v1/anomalies`, `/sectors`, `/analyze`)
- [x] WebSocket 실시간 이상값 브로드캐스트 (`/ws/live`)
- [x] APScheduler 60분마다 자동 분석
- [x] Swagger UI (`http://localhost:8000/docs`)

---

## Phase 2 — 프론트엔드 대시보드 (완료 ✅)

- [x] Next.js 14 App Router + Tailwind CSS
- [x] 섹터 히트맵 (이상값 빈도 색상 표현)
- [x] 이상값 목록 실시간 업데이트 (WebSocket)
- [x] 분봉 가격 차트 (실제 가격선 + 이상값 마커, 1D/3D/5D 기간 선택)
- [x] 종목 검색바 — 기업명/티커 코드로 임의 종목 조회
- [x] 기업명 표시 — NVDA → NVIDIA, KR:005930 → 삼성전자 (KR: 접두사 정규화)
- [x] AI 분석 리포트 한국어/영어 탭 전환
- [x] 수동 분석 트리거 + 진행 상태 표시
- [x] AI 분석 없음 / 미선택 상태 구분 표시

---

## Phase 3 — Kafka 파이프라인 (완료 ✅)

### Kafka Topic 설계
```
stock.raw.us        미국 1분봉 배치 (yfinance, 60초 루프)
stock.raw.kr        한국 1분봉 배치 (KIS WebSocket 집계)
anomaly.detected    이상값 감지 결과
news.fetched        뉴스 수집 완료 이벤트
analysis.completed  AI 분석 완료 결과
```

### 서비스별 Kafka 흐름
```
[stock-collector]   →  stock.raw.us
[kis-bridge]        →  stock.raw.kr
[anomaly-detector]  ←  stock.raw.*  →  anomaly.detected
[news-fetcher]      ←  anomaly.detected  →  news.fetched
[ai-analyzer]       ←  news.fetched  →  analysis.completed
[api]               ←  analysis.completed  →  DB 저장 + WS 브로드캐스트
[notifier]          ←  analysis.completed  →  Slack 알림
```

### Gemini 응답 파싱
- 정상: `---[한국어 분석]---` / `---[English Analysis]---` 구분자로 분리
- 구분자 누락 시: 존재하는 섹션만 저장, 없는 언어는 빈 문자열 (잘못된 fallback 수정됨)

### 10개 섹터 구성

| 섹터 | US ETF | KR ETF | 대표 종목 |
|------|--------|--------|-----------|
| 반도체 | SMH, SOXX | KODEX 반도체 | NVDA, TSM / 삼성전자, SK하이닉스 |
| 기술/SW | XLK, QQQ | KODEX IT | MSFT, AAPL / NAVER, 카카오 |
| 금융 | XLF, KRE | KODEX 은행 | JPM, BAC / KB금융, 신한지주 |
| 에너지 | XLE, XOP | KODEX 에너지화학 | XOM, CVX / S-Oil, SK이노베이션 |
| 헬스케어 | XLV, IBB | KODEX 바이오 | UNH, LLY / 삼성바이오, 셀트리온 |
| 전기차/배터리 | LIT, DRIV | KODEX 2차전지 | TSLA, GM / LG에너지, 삼성SDI |
| 방산/항공 | ITA, XAR | TIGER 우주방산 | LMT, RTX / 한화에어로, 한국항공우주 |
| 소재/철강 | XLB, PICK | KODEX 철강 | FCX, LIN / POSCO, 고려아연 |
| 부동산 | XLRE, VNQ | TIGER 리츠 | AMT, PLD / 현대건설, 삼성물산 |
| 소비재 | XLY, XLP | KODEX 200중소형 | AMZN, WMT / 이마트, 롯데쇼핑 |

---

## Phase 4 — Docker & Kubernetes (완료 ✅)

### K8s 리소스 구성
```yaml
# Deployment
api             replicas: 1   # WebSocket 인메모리 관리 (Redis pub/sub 도입 전 단일)
ai-analyzer     replicas: 2   # HPA: CPU 70% → 최대 5개
anomaly-detector replicas: 2
frontend        replicas: 2

# StatefulSet
kafka           replicas: 3
timescaledb     replicas: 1
redis           replicas: 1

# 상시 실행
stock-collector replicas: 1
kis-bridge      replicas: 1
```

### CI/CD 흐름
```
코드 push (main)
    → GitHub Actions: 이미지 빌드 → Harbor push → k8s 태그 업데이트 commit
    → ArgoCD: k8s/ 변경 감지 → K8s Rolling Update (다운타임 0)
```

### Secrets 구성
| Secret | 용도 |
|--------|------|
| `stock-db-secret` | DB 접속 정보 |
| `stock-api-secrets` | GEMINI_API_KEY, NEWS_API_KEY |
| `stock-kis-secret` | KIS_APP_KEY, KIS_APP_SECRET, KIS_MOCK |

> `stock-kis-secret`은 api deployment에도 주입 — KR 1D 분봉 조회에 사용

---

## Phase 5 — 개인화 서비스 POC (진행중 🔄)

### 목표
기관 수준의 AI 분석을 **개인 투자자 관점**으로 재해석. 내 포트폴리오에서 이상값이 발생하면 즉시 AI가 원인을 분석하고 손익 영향을 계산해주는 서비스.

### 구현 완료 항목
- [x] **관심 종목 (Watchlist)** — ★ 버튼으로 추가/제거, Zustand persist (localStorage 영속)
- [x] **내 종목만 필터** — 이상값 목록에서 관심 종목 이상값만 표시
- [x] **포트폴리오 패널** — 수량 + 평균단가 입력
- [x] **실시간 손익 계산** — KIS REST API / yfinance로 현재가 조회 (60초 자동 갱신)
- [x] **PortfolioPanel 레이아웃** — 기존 3열 상단 배치 (섹터히트맵 / 이상값목록 / 포트폴리오)

### 향후 추가 예정 항목
- [ ] **알림 임계값 설정** — 종목별 몇 % 이상 변동 시에만 알림
- [ ] **목표가 / 손절가 설정** — 해당 가격 도달 시 하이라이트
- [ ] **포트폴리오 섹터 분산 차트** — 보유 종목의 섹터 비중 파이 차트
- [ ] **이상값 히트율 통계** — 과거 이상값 발생 후 n일 뒤 수익률 통계
- [ ] **이메일 / 카카오 알림** — 내 종목 이상값 발생 시 외부 채널 발송
- [ ] **회원가입 / 로그인** — 서버사이드 포트폴리오 저장 (현재는 localStorage)

---

## 9. 최종 아키텍처 다이어그램

```
                    [ 사용자 브라우저 ]
                           │
                    ┌──────▼──────┐
                    │   Ingress   │  (nginx)
                    └──┬───────┬──┘
                       │       │
              ┌────────▼─┐ ┌───▼────────────┐
              │ Frontend  │ │  API Server    │
              │ Next.js   │ │  FastAPI       │
              │           │ │                │
              └───────────┘ └───┬────────┬───┘
                                │  WebSocket
                         ┌──────▼──────────────────────────┐
                         │           Apache Kafka           │
                         └──┬──────┬──────┬──────┬─────────┘
                    ┌───────┘  ┌───┘  ┌───┘  └──────────┐
              ┌─────▼───┐ ┌────▼──┐ ┌──▼──────┐ ┌───────▼──┐
              │Stock    │ │News   │ │AI       │ │Notifier  │
              │Collector│ │Fetcher│ │Analyzer │ │(Slack)   │
              │+Detector│ │       │ │(Gemini) │ │          │
              └────┬────┘ └───────┘ └─────────┘ └──────────┘
                   │
              ┌────▼──────────────────────┐
              │  TimescaleDB  │  Redis     │
              └───────────────────────────┘
                   │
              ┌────▼──────────────────┐
              │  Prometheus + Grafana │
              └───────────────────────┘
```

---

## 10. DB 스키마 설계

### TimescaleDB
```sql
CREATE TABLE anomalies (
    id                   SERIAL PRIMARY KEY,
    detected_at          TIMESTAMPTZ DEFAULT NOW(),
    ticker               VARCHAR(20) NOT NULL,
    anomaly_date         DATE        NOT NULL,
    bar_timestamp        VARCHAR(30),           -- 1분봉 정확한 시각
    return_pct           DOUBLE PRECISION NOT NULL,
    zscore               DOUBLE PRECISION,
    close_price          DOUBLE PRECISION,
    volume               BIGINT,
    direction            VARCHAR(10) NOT NULL,  -- '급등' or '급락'
    is_etf               BOOLEAN DEFAULT FALSE,
    event_type           VARCHAR(20) NOT NULL,  -- 'INDIVIDUAL', 'SECTOR', 'MARKET'
    sector               VARCHAR(100),
    sector_peer_count    INT,
    moving_sector_count  INT
);

CREATE TABLE analysis_results (
    id          SERIAL PRIMARY KEY,
    anomaly_id  INT UNIQUE REFERENCES anomalies(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    analysis_ko TEXT NOT NULL,
    analysis_en TEXT NOT NULL,
    news_en     JSON DEFAULT '[]',
    news_kr     JSON DEFAULT '[]'
);
```

> `anomalies`에 `analysis_id` 컬럼 없음.
> API의 `AnomalyResponse`는 `has_analysis: bool` (JOIN 여부)을 반환.
> 프론트엔드는 `has_analysis=true`이면 `anomaly.id`로 `/analysis` 엔드포인트 호출.

---

## 11. API 명세

```
GET  /api/v1/anomalies
     Query: ?days=7&sector=반도체&event_type=SECTOR&limit=20
     Response: [{ id, ticker, anomaly_date, return_pct, direction, event_type,
                  sector, has_analysis, detected_at, ... }]

GET  /api/v1/anomalies/{ticker}/history
     Query: ?days=30

GET  /api/v1/anomalies/{anomaly_id}/analysis
     Response: { id, anomaly_id, analysis_ko, analysis_en, news_en[], news_kr[] }

GET  /api/v1/sectors/trending
     Query: ?days=7
     Response: [{ sector, anomaly_count, avg_return_pct, up_count, down_count, hot_tickers }]

GET  /api/v1/stocks/{ticker}/candles
     Query: ?days=1  (1~5일)
     - US: yfinance 1분봉
     - KR days=1: KIS REST API 분봉 (inquire-time-itemchartprice, 14회 페이징)
     - KR days>1: pykrx 일봉
     Response: [{ timestamp, open, high, low, close, volume }]

POST /api/v1/analyze/trigger
     Response: { job_id, status: "queued" }

GET  /api/v1/analyze/jobs/{job_id}
     Response: { status, started_at, completed_at, anomaly_count }

WS   /ws/live
     Server → Client: { type: "anomaly", ticker, return_pct, sector, event_type }
```

---

## 12. 향후 로드맵

> 전략: 무료 바이럴 → 프리미엄 전환 → B2B API 확장

---

### Phase 6 — 사용자 인증 & 서버사이드 포트폴리오 [현재 Step]
> 수익화의 전제조건. 회원 없이는 유료 전환 불가.

**DB 추가 테이블**
```sql
users          -- id, email, password_hash, tier, created_at
watchlists     -- id, user_id, ticker, added_at
portfolios     -- id, user_id, ticker, quantity, avg_price, added_at
alert_settings -- id, user_id, ticker, threshold_pct, alert_channel
```

**구현 항목**
- [ ] `services/auth/` 마이크로서비스 신설 (FastAPI)
  - [ ] POST `/auth/register` — 이메일 + 비밀번호 회원가입
  - [ ] POST `/auth/login` — JWT Access Token (15분) + Refresh Token (30일) 발급
  - [ ] POST `/auth/refresh` — Access Token 재발급
  - [ ] GET  `/auth/me` — 현재 유저 정보
- [ ] TimescaleDB에 `users`, `watchlists`, `portfolios`, `alert_settings` 테이블 추가
- [ ] API 서버 미들웨어 — JWT 검증 (`Authorization: Bearer ...`)
- [ ] 프론트엔드 로그인 / 회원가입 페이지
- [ ] Zustand 관심종목 & 포트폴리오 → 서버 API로 마이그레이션 (localStorage 병행)
- [ ] K8s Secret — JWT_SECRET 추가

**성공 기준:** 회원가입 → 로그인 → 관심 종목이 서버에 저장되고 재접속 시 유지

---

### Phase 7 — 카카오 알림톡 & 맞춤 알림 [2단계]
> 한국 투자자 킬러 피처. 바이럴의 핵심.

**구현 항목**
- [ ] 카카오 알림톡 API 연동 (`notifier` 서비스 확장)
  - 메시지 형식: `[StockPulse] NVDA 3.2% 급등 감지 — AI 분석 보기 →`
- [ ] 이메일 알림 (SendGrid / AWS SES)
- [ ] 브라우저 Push Notification (PWA Service Worker)
- [ ] `alert_settings` 기반 개인화 필터
  - 종목별 알림 임계값 (예: 내 NVDA는 5% 이상만 알림)
  - 알림 채널 선택 (카카오 / 이메일 / 브라우저)
  - 조용한 시간대 설정 (22:00~08:00 알림 차단)
- [ ] `notifier` 서비스 → Kafka `analysis.completed` 소비 시 유저별 필터링 후 발송

**성공 기준:** 이상값 발생 → 해당 종목 보유 유저에게 카카오 알림 발송 (1분 이내)

---

### Phase 8 — 수익화 티어 구현 [3단계]
> 유저가 모이면 수익 구조를 잠근다.

**티어 설계**

| 티어 | 기능 | 가격 |
|------|------|------|
| 무료 (Free) | 이상값 일 10건, 관심종목 5개, AI 분석 열람 | 0원 |
| 스탠다드 | 무제한 이상값, 관심종목 무제한, 카카오/이메일 알림 | 월 9,900원 |
| 프로 | + 이상값 히트율 통계, 알림 임계값, 목표가/손절가 알림 | 월 19,900원 |
| 기업 (API) | REST API 키 발급, 커스텀 섹터, SLA 99.9% | 월 협의 |

**구현 항목**
- [ ] `users.tier` 필드 (`free` / `standard` / `pro` / `enterprise`)
- [ ] API 레이어 — 티어별 rate limit 미들웨어
- [ ] 결제 연동 — 토스페이먼츠 또는 포트원(아임포트)
- [ ] 구독 관리 페이지 (프론트엔드)
- [ ] 무료 티어 일일 한도 초과 시 업그레이드 유도 모달

**성공 기준:** 유료 유저 100명 첫 달성

---

### Phase 9 — 이상값 히트율 & 포트폴리오 고도화 [4단계]
> 프로 티어 락인 기능. 데이터 기반 신뢰도.

**이상값 히트율 통계 (시그널 신뢰도)**
- 과거 이상값 발생 후 1일 / 3일 / 5일 / 10일 수익률 추적
- 예시: `NVDA 급등 시그널 → 3일 후 평균 +2.8% (23건 중 17건 적중, 74%)`
- DB: `signal_outcomes` 테이블 (anomaly_id, day_1_return, day_3_return, day_5_return)
- 배치 스케줄러: 매일 전날 이상값의 현재가 조회 후 수익률 기록

**포트폴리오 고도화**
- [ ] 섹터 분산 현황 파이 차트
- [ ] 목표가 / 손절가 알림
- [ ] 보유 종목 이상값 발생 시 AI 리포트에 포트폴리오 영향 자동 추가
  - 예: "현재 NVDA 100주 보유 중. 이번 급등으로 예상 평가이익: +₩320만"

**성공 기준:** 프로 유저 전환율 스탠다드 대비 30% 이상

---

### Phase 10 — 데이터 고도화 & ML 탐지 [5단계]
> 이상값 탐지의 정확도를 높여 데이터 자체가 경쟁 우위가 됨.

- [ ] 공시/DART 연동 — 이상값 발생 시 관련 공시 자동 매핑
- [ ] 자체 이상값 탐지 모델 (Z-score → Isolation Forest → LSTM)
- [ ] 이상값 예측 (발생 전 선행 지표: 거래량 급증, 호가창 불균형)
- [ ] 옵션 IV (내재변동성) 데이터 — 미국 주식 변동성 예측 보조
- [ ] 공매도 잔고 데이터 연동 (한국: 금융위 공시)

**성공 기준:** 탐지 정확도 지표 수립 + 기존 Z-score 대비 false positive 30% 감소

---

### Phase 11 — B2B API 마켓플레이스 [6단계]
> 개인 구독보다 단가 높은 B2B. 연 매출 2배 레버리지.

- [ ] API 키 발급 시스템 (기업 회원 전용)
- [ ] API 문서 포털 (Swagger + 가이드 페이지)
- [ ] Rate limit 티어: 기본 1,000건/일 → 협의 무제한
- [ ] 웹훅 발송 — 이상값 발생 시 고객사 서버로 실시간 Push
- [ ] 타겟 고객
  - 증권사 리서치팀 (이상값 데이터 납품)
  - 자산운용사 (시그널 데이터 정기 구독)
  - 핀테크 앱 (토스증권, 카카오페이증권) 화이트라벨링

**성공 기준:** 기업 고객 3개사 계약

---

### Phase 12 — 글로벌 확장 [7단계]
> 한국/미국 이중 커버리지를 무기로 아시아 시장 공략.

- [ ] 일본 주식 연동 (JPX — Yahoo Finance Japan)
- [ ] 중국 A주 연동 (AkShare 오픈소스)
- [ ] 영어 UI 완성 (현재 한/영 분석 리포트는 존재)
- [ ] 해외 결제 (Stripe)
- [ ] SEO 최적화 (이상값 리포트 페이지 공개 → 검색 유입)

---

## 개발 우선순위 요약

| 단계 | 상태 | 핵심 가치 |
|------|------|-----------|
| Phase 1 (FastAPI + DB) | ✅ 완료 | DB 저장 + API 조회 |
| Phase 2 (Frontend) | ✅ 완료 | 시각적 대시보드 + 실시간 알림 |
| Phase 3 (Kafka) | ✅ 완료 | 안정적 파이프라인 + 확장성 |
| Phase 4 (K8s + CI/CD) | ✅ 완료 | GitOps 자동 배포 + 모니터링 |
| Phase 5 (개인화 POC) | 🔄 진행중 | 관심 종목 + 포트폴리오 손익 |
| **Phase 6 (인증)** | **⬅ 현재** | **멀티 유저 + 서버사이드 저장** |
| Phase 7 (카카오 알림) | 📋 예정 | 카카오/이메일 + 임계값 설정 |
| Phase 8 (수익화 티어) | 📋 예정 | 결제 + 티어 제한 |
| Phase 9 (히트율 + 포폴 고도화) | 📋 예정 | 시그널 신뢰도 + 프로 락인 |
| Phase 10 (ML 탐지 + 공시) | 📋 예정 | 탐지 정확도 향상 |
| Phase 11 (B2B API) | 📋 예정 | 기업 고객 + 화이트라벨 |
| Phase 12 (글로벌) | 📋 예정 | 일/중 주식 + 해외 결제 |
