# StockPulse — 주식 이상값 AI 분석 플랫폼

전 세계 주식 시장의 **급등/급락 이벤트**를 실시간으로 감지하고, 영문/한국어 뉴스를 기반으로 **Gemini AI가 원인을 분석**해 사용자에게 전달하는 MSA 기반 플랫폼입니다.

---

## 핵심 기능

- **실시간 이상값 감지** — 미국(yfinance 1분봉) + 한국(KIS WebSocket) 주식 동시 모니터링
- **이벤트 자동 분류** — ETF 기반 로직으로 INDIVIDUAL / SECTOR / MARKET 이벤트 구분
- **AI 원인 분석** — Gemini 2.5 Flash로 관련 뉴스 수집 후 한국어 + 영어 리포트 생성
- **실시간 대시보드** — WebSocket 기반 섹터 히트맵, 이상값 목록, AI 분석 리포트
- **분봉 차트** — 실제 가격선 위에 이상값 발생 위치를 마커로 표시 (1D/3D/5D 선택)
  - 미국: yfinance 1분봉 / 한국 1D: KIS REST API 분봉 / 한국 3D·5D: pykrx 일봉
- **종목 검색** — 이상값 외 임의 종목을 기업명/티커 코드로 검색해 차트 조회
- **기업명 표시** — 티커 코드 대신 기업명으로 종목 식별 (NVDA → NVIDIA, KR:005930 → 삼성전자)
- **관심 종목 (Watchlist)** — ★로 종목 추가, 내 종목만 필터, 브라우저 재시작 후에도 유지
- **포트폴리오 손익 추적** — 수량·평균단가 입력 → 현재가 실시간 조회 → 손익 자동 계산
- **Slack 알림** — 이상값 감지 즉시 분석 결과 발송

---

## 아키텍처

```
                    [ 사용자 브라우저 ]
                           │
                    ┌──────▼──────┐
                    │   Ingress   │  (nginx)
                    └──┬───────┬──┘
                       │       │
              ┌────────▼─┐ ┌───▼────────────┐
              │ Frontend  │ │  API Server    │
              │ Next.js   │ │  FastAPI × 2   │
              └───────────┘ └───┬────────┬───┘
                                │        │ WebSocket
                    ┌───────────▼────────────────────────┐
                    │            Apache Kafka             │
                    │     stock.raw → anomaly.detected    │
                    │     → news.fetched → analysis.done  │
                    └────┬──────┬──────┬──────┬──────────┘
                         │      │      │      │
               ┌─────────▼─┐ ┌──▼──┐ ┌─▼──────────┐ ┌──────────┐
               │  Stock    │ │News │ │ AI Analyzer │ │Notifier  │
               │ Collector │ │Ftchr│ │ (Gemini)    │ │(Slack)   │
               │ Detector  │ └─────┘ └─────────────┘ └──────────┘
               └─────┬─────┘
                     │
          ┌──────────▼─────────────┐
          │  TimescaleDB  │  Redis  │
          └────────────────────────┘
                     │
          ┌──────────▼─────────────┐
          │  Prometheus + Grafana  │
          └────────────────────────┘
```

### Kafka 파이프라인 흐름

```
[stock-collector]  →  stock.raw.us  (yfinance 1분봉, 60초 루프)
[kis-bridge]       →  stock.raw.kr  (KIS WebSocket 실시간 체결 → 1분봉 집계)
[anomaly-detector] ←  stock.raw.*   →  anomaly.detected  (Z-score + % 임계값)
[news-fetcher]     ←  anomaly.detected  →  news.fetched  (NewsAPI + 네이버 RSS)
[ai-analyzer]      ←  news.fetched   →  analysis.completed  (Gemini 2.5 Flash)
[api]              ←  analysis.completed  →  DB 저장 + WebSocket 브로드캐스트
[notifier]         ←  analysis.completed  →  Slack Webhook 발송
```

---

## 기술 스택

### Backend
| 역할 | 기술 |
|------|------|
| API 서버 | FastAPI + uvicorn |
| 메시지 큐 | Apache Kafka (confluent-kafka) |
| 시계열 DB | TimescaleDB (PostgreSQL 확장) |
| ORM | SQLAlchemy (async) + asyncpg |
| 캐시 | Redis |
| AI | Gemini 2.5 Flash |
| 스케줄러 | APScheduler (Kafka 없을 때 fallback) |
| 모니터링 | Prometheus + Grafana |

### Frontend
| 역할 | 기술 |
|------|------|
| 프레임워크 | Next.js 14 (App Router) |
| 상태관리 | Zustand (+ persist 미들웨어) |
| 차트 | Recharts (분봉 가격선 + 이상값 마커) |
| 실시간 | WebSocket (native) |
| 스타일 | Tailwind CSS |
| 종목 검색 | 클라이언트 사이드 (tickerNames.ts, KR: 접두사 정규화) |
| 관심 종목 | Zustand persist → localStorage 영속 |
| 포트폴리오 | 현재가 실시간 조회 + 손익 자동 계산 |

### Data
| 역할 | 기술 |
|------|------|
| 미국 주가 | yfinance 1분봉 polling |
| 한국 실시간 | 한국투자증권 KIS WebSocket |
| 한국 분봉 차트 | KIS REST API (inquire-time-itemchartprice) |
| 한국 일봉 | pykrx |
| 영문 뉴스 | NewsAPI + Google RSS |
| 한국 뉴스 | 네이버 뉴스 RSS |

### Infrastructure
| 역할 | 기술 |
|------|------|
| 컨테이너 | Docker |
| 오케스트레이션 | Kubernetes |
| CI | GitHub Actions (self-hosted runner) |
| CD | ArgoCD (GitOps) |
| 이미지 레지스트리 | Harbor (self-hosted) |

---

## 섹터 구성 (10개 섹터)

ETF를 "섹터 체온계"로 사용해 노이즈를 줄이고 섹터 방향성 시그널에 집중하는 설계입니다.

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

**이벤트 분류 로직:**
```
ETF 여러 개 동시 이상값    → MARKET    (시장 전체 이벤트)
해당 섹터 ETF 이상값       → SECTOR    (섹터 이벤트)
여러 개별 종목 동시 이동   → SECTOR
그 외                      → INDIVIDUAL
```

---

## CI/CD 파이프라인

```
코드 push (main)
    │
    ▼
GitHub Actions (self-hosted runner)
    ├── 서비스별 Docker 이미지 빌드 (8개)
    ├── Harbor 레지스트리에 push (:latest + :<git-sha>)
    └── k8s/ 매니페스트 이미지 태그 업데이트 → git commit
            │
            ▼
    ArgoCD (GitOps)
    ├── k8s/ 디렉토리 변경 감지
    └── K8s 클러스터 Rolling Update → 다운타임 0
```

---

## 빠른 시작 (로컬 Docker Compose)

### 사전 요구사항
- Docker & Docker Compose
- Gemini API Key ([Google AI Studio](https://aistudio.google.com) 무료 발급)
- NewsAPI Key ([newsapi.org](https://newsapi.org) 무료 발급)

### 실행

```bash
# 1. 저장소 클론
git clone https://github.com/ION127/StockPulse.git
cd StockPulse

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 아래 값 입력:
#   GEMINI_API_KEY=...
#   NEWS_API_KEY=...

# 3. 전체 서비스 실행 (최초 빌드 약 3~5분)
docker compose up --build

# 4. 접속
# 대시보드:  http://localhost:3000
# API 문서:  http://localhost:8000/docs
```

### 한국 주식 실시간 연동 (선택)

[한국투자증권 Open API](https://apiportal.koreainvestment.com) 앱키 발급 후:

```bash
# .env에 추가
KIS_APP_KEY=<앱키>
KIS_APP_SECRET=<앱시크릿>
KIS_MOCK=false   # 모의투자 테스트: true

docker compose up kis-bridge
```

> KIS_APP_KEY 미설정 시 미국 주식만 동작합니다.

---

## K8s 배포 구성

```yaml
# 상태 없는 서비스 (Deployment)
api-server          replicas: 2   # HPA: 요청 증가 시 자동 스케일
ai-analyzer         replicas: 2   # HPA: CPU 70% 초과 시 최대 5개
anomaly-detector    replicas: 2
frontend            replicas: 2

# 상시 실행 (1분봉 루프)
stock-collector     replicas: 1
kis-bridge          replicas: 1

# 인프라 (StatefulSet)
kafka               replicas: 3   # 브로커 클러스터
timescaledb         replicas: 1
redis               replicas: 1
```

### ArgoCD 앱 배포

```bash
kubectl apply -f argocd/application.yaml
```

이후 `k8s/` 디렉토리 변경사항이 감지되면 자동으로 클러스터에 반영됩니다.

---

## API 명세

```
GET  /api/v1/anomalies
     ?days=7&sector=반도체&event_type=SECTOR&limit=20

GET  /api/v1/anomalies/{ticker}/history
     ?days=30

GET  /api/v1/anomalies/{anomaly_id}/analysis

GET  /api/v1/sectors/trending
     ?days=7
     → [{ sector, anomaly_count, avg_return_pct, up_count, down_count, hot_tickers }]

GET  /api/v1/stocks/{ticker}/candles
     ?days=1  (1~5일)
     → 미국: yfinance 1분봉
     → 한국 days=1: KIS REST API 분봉
     → 한국 days>1: pykrx 일봉
     → [{ timestamp, open, high, low, close, volume }]

POST /api/v1/analyze/trigger
     → { job_id, status: "queued" }

GET  /api/v1/analyze/jobs/{job_id}
     → { status, started_at, completed_at, anomaly_count }

WS   /ws/live
     → { type: "anomaly", ticker, return_pct, sector, event_type }
```

전체 명세: `http://localhost:8000/docs` (Swagger UI)

---

## 프로젝트 구조

```
StockPulse/
├── core/                    # 공유 Python 모듈
│   ├── stock_categories.py  # 10개 섹터 종목 정의
│   ├── stock_fetcher.py     # yfinance + 이상값 탐지
│   ├── news_fetcher.py      # NewsAPI + 네이버 RSS
│   └── ai_analyzer.py       # Gemini API 래퍼
├── services/
│   ├── api/                 # FastAPI (REST + WebSocket + Kafka consumer)
│   │   └── routers/
│   │       ├── anomalies.py # 이상값 조회 API
│   │       ├── sectors.py   # 섹터 트렌드 API
│   │       ├── jobs.py      # 수동 분석 트리거 API
│   │       └── stocks.py    # 분봉 데이터 API (신규)
│   ├── stock-collector/     # yfinance → stock.raw.us
│   ├── kis-bridge/          # KIS WebSocket → stock.raw.kr
│   ├── anomaly-detector/    # 이상값 탐지 → anomaly.detected
│   ├── news-fetcher/        # 뉴스 수집 → news.fetched
│   ├── ai-analyzer/         # Gemini 분석 → analysis.completed
│   └── notifier/            # Slack 알림
├── frontend/                # Next.js 14 대시보드
│   ├── app/components/
│   │   ├── SearchBar.tsx      # 종목 검색 + ★ 관심 종목 토글
│   │   ├── StockChart.tsx     # 분봉 차트 + 이상값 마커 (1D/3D/5D)
│   │   ├── AnomalyList.tsx    # 이상값 목록 (★버튼, 내 종목만 필터)
│   │   ├── AnalysisPanel.tsx  # AI 분석 한/영 탭
│   │   ├── PortfolioPanel.tsx # 관심 종목 + 포트폴리오 손익
│   │   └── ...
│   └── lib/
│       ├── tickerNames.ts     # 티커↔기업명 매핑 (KR: 접두사 정규화)
│       └── watchlistStore.ts  # 관심 종목 + 포트폴리오 (persist)
├── k8s/                     # Kubernetes 매니페스트
├── argocd/                  # ArgoCD GitOps 설정
├── monitoring/              # Prometheus + Grafana 대시보드
├── DFD.md                   # 데이터 흐름도
└── docker-compose.yml
```

---

## 환경변수 요약

| 변수 | 설명 | 필수 |
|------|------|------|
| `GEMINI_API_KEY` | Gemini AI API 키 | ✅ |
| `NEWS_API_KEY` | NewsAPI 키 (영문 뉴스) | ✅ |
| `KIS_APP_KEY` | 한국투자증권 앱키 | 한국 주식 사용 시 |
| `KIS_APP_SECRET` | 한국투자증권 앱시크릿 | 한국 주식 사용 시 |
| `KIS_MOCK` | 모의투자 모드 (`true`/`false`) | 선택 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | 선택 |
| `ANOMALY_THRESHOLD_PERCENT` | 이상값 % 임계값 (기본: `1.5`) | 선택 |
| `ANOMALY_ZSCORE_THRESHOLD` | Z-score 임계값 (기본: `3.0`) | 선택 |
