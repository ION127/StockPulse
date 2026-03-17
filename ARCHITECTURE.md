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
│   │   │   ├── anomalies.py       #   GET /api/v1/anomalies
│   │   │   ├── sectors.py         #   GET /api/v1/sectors/trending
│   │   │   └── jobs.py            #   POST /api/v1/analyze/trigger
│   │   ├── schemas/
│   │   │   └── anomaly.py         #   Pydantic 요청/응답 모델
│   │   └── services/
│   │       └── pipeline.py        #   수집→탐지→저장→AI분석 파이프라인
│   │
│   ├── stock-collector/           # Phase 3: 미국 1분봉 → Kafka 'stock.raw.us' (60초 루프)
│   │   ├── Dockerfile
│   │   └── main.py
│   │
│   ├── kis-bridge/                # 한국 실시간 → Kafka 'stock.raw.kr' [Docker 가능]
│   │   ├── Dockerfile             #   Linux 기반, HTS 불필요
│   │   ├── main.py                #   한국투자증권 WebSocket, asyncio
│   │   └── requirements.txt       #   aiohttp, websockets, confluent-kafka
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
├── docker-compose.yml             # 로컬 통합 실행 (전 서비스 활성)
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
| `kis-bridge` | `.` (루트) | `services/kis-bridge/Dockerfile` | `core/` 접근 필요 |
| `notifier` | `.` (루트) | `services/notifier/Dockerfile` | `core/` 접근 불필요, 독립 |
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
| 주가 (미국) | **yfinance 1분봉** | 무료, 1분봉 polling, 5일치 Z-score 계산 |
| 주가 (한국) | **한국투자증권 KIS WebSocket** | 실시간 체결 → 1분봉 집계, HTS 불필요, Docker 가능 |
| 종목 구성 | **섹터 ETF + 시가총액 상위주** | 예측 불가 개별 이벤트 제거, 섹터 시그널 집중 |
| 뉴스 (영문) | **NewsAPI + Google RSS** | 무료 티어 존재 |
| 뉴스 (한국) | **네이버 뉴스 RSS** | 무료 |

### Infrastructure
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| 컨테이너 | **Docker** | 환경 일치, 배포 표준 |
| 오케스트레이션 | **Kubernetes (K8s)** | 자동 스케일링, 자가복구, 무중단 배포 |
| CI | **GitHub Actions** | 빌드·테스트·이미지 빌드+Harbor 푸시 자동화 |
| CD | **ArgoCD** | GitOps 방식, K8s 매니페스트 변경 감지 → 자동 배포 |
| 이미지 레지스트리 | **Harbor** (로컬 self-hosted) | 사내 이미지 관리, 보안 스캔, 외부 의존 없음 |
| 모니터링 | **Prometheus + Grafana** | K8s 표준 모니터링 스택, 서비스별 메트릭 대시보드 |
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
stock.raw.us        미국 1분봉 배치 (yfinance, 60초 루프)    — key: "batch"
stock.raw.kr        한국 1분봉 배치 (KIS WebSocket 집계)     — key: "realtime"
anomaly.detected    이상값 감지 결과                        — key: ticker
news.fetched        뉴스 수집 완료 이벤트                    — key: ticker
analysis.completed  AI 분석 완료 결과                       — key: ticker
```

### 섹터 구성 전략 (ETF + 시가총액 상위주)

개별 종목의 예측 불가 이벤트(계약 분쟁, 스캔들 등) 노이즈를 제거하고
**섹터 전체 방향성**에 집중하는 설계.

| 역할 | 설명 | 예시 |
|------|------|------|
| **섹터 ETF** | 섹터 체온계 — ETF 이상값 = 섹터 이벤트 확정 | SMH(반도체), XLF(금융), LIT(배터리) |
| **시가총액 상위주** | 확인 신호 + 알파 — ETF와 함께 움직이면 강한 시그널 | NVDA, TSM, 삼성전자, SK하이닉스 |

**10개 섹터 구성:**

| 섹터 | US ETF | KR ETF | 대표 종목 (US / KR) |
|------|--------|--------|-------------------|
| 반도체 | SMH, SOXX | KODEX 반도체(091160) | NVDA, TSM / 삼성전자, SK하이닉스 |
| 기술/SW | XLK, QQQ | KODEX IT(098560) | MSFT, AAPL / NAVER, 카카오 |
| 금융 | XLF, KRE | KODEX 은행(091170) | JPM, BAC / KB금융, 신한지주 |
| 에너지 | XLE, XOP | KODEX 에너지화학(117460) | XOM, CVX / S-Oil, SK이노베이션 |
| 헬스케어 | XLV, IBB | KODEX 바이오(244580) | UNH, LLY / 삼성바이오, 셀트리온 |
| 전기차/배터리 | LIT, DRIV | KODEX 2차전지(305720) | TSLA, GM / LG에너지, 삼성SDI |
| 방산/항공 | ITA, XAR | TIGER 우주방산(475050) | LMT, RTX / 한화에어로, 한국항공우주 |
| 소재/철강 | XLB, PICK | KODEX 철강(138540) | FCX, LIN / POSCO, 고려아연 |
| 부동산 | XLRE, VNQ | TIGER 리츠(352560) | AMT, PLD / 현대건설, 삼성물산 |
| 소비재 | XLY, XLP | KODEX 200중소형(266390) | AMZN, WMT / 이마트, 롯데쇼핑 |

**ETF 인식 이벤트 분류 로직:**
```
ETF 여러 개 동시 이상값    → MARKET  (시장 전체 이벤트, 강제)
해당 섹터 ETF 이상값       → SECTOR  (섹터 이벤트, 강제 상향)
여러 개별 종목 함께 움직임 → SECTOR
그 외                      → INDIVIDUAL
```

### 데이터 수집 방식
| 시장 | 방식 | 주기 | 서비스 | 실행 환경 |
|------|------|------|--------|----------|
| 미국 (US) | yfinance 1분봉 polling | 60초 루프 | `stock-collector` | Docker |
| 한국 (KR) | 한국투자증권 KIS WebSocket 실시간 체결 → 1분봉 집계 | 체결 즉시 수신 | `kis-bridge` | Docker |

### 서비스별 Kafka 흐름
```
[stock-collector]   →  stock.raw.us 발행 (1분봉, 60초 루프)         [Docker]
[kis-bridge]        →  stock.raw.kr 발행 (실시간→1분봉 집계)         [Docker]
[anomaly-detector]  ←  stock.raw.* 구독  →  anomaly.detected 발행
[news-fetcher]      ←  anomaly.detected 구독  →  news.fetched 발행
[ai-analyzer]       ←  news.fetched 구독  →  analysis.completed 발행
[api (db-writer)]   ←  analysis.completed 구독  →  DB 저장 + WS 브로드캐스트
[notifier]          ←  analysis.completed 구독  →  Slack 알림 발송
```

### 메시지 스키마
| Topic | 주요 필드 |
|-------|-----------|
| `stock.raw.*` | `market, timestamp, stocks: {ticker: {"YYYY-MM-DD HH:MM:SS": {OHLCV}}}` |
| `anomaly.detected` | `ticker, date, bar_timestamp, return_pct, zscore, direction, is_etf, event_type, sector, sector_peer_count, moving_sector_count` |
| `news.fetched` | anomaly 필드 + `news_en[], news_kr[], news_text` |
| `analysis.completed` | news 필드 - news_text + `analysis_ko, analysis_en` |

### 구현 완료 항목
- [x] Kafka + Zookeeper 컨테이너 (`docker-compose.yml` 활성화)
- [x] `stock-collector/main.py` — yfinance 1분봉, 60초 루프, stock.raw.us 발행
- [x] `kis-bridge/main.py` — 한국투자증권 KIS WebSocket 실시간 체결 → 1분봉 집계 → stock.raw.kr 발행 (Docker)
- [x] `anomaly-detector/main.py` — stock.raw.* 구독 → 탐지+분류 → anomaly.detected (`INTRADAY_RECENT_MINUTES` 필터)
- [x] `news-fetcher/main.py` — anomaly.detected 구독 → 뉴스 수집 → news.fetched
- [x] `ai-analyzer/main.py` — news.fetched 구독 → Gemini 분석 → analysis.completed
- [x] `notifier/main.py` — analysis.completed 구독 → Slack Webhook 발송
- [x] `api/main.py` — analysis.completed 구독 → DB 저장 + WebSocket 브로드캐스트
- [x] `requirements.txt`에 `confluent-kafka>=2.4.0` 추가
- [x] API는 Kafka 없을 때 APScheduler pipeline.py fallback 유지 (하위 호환)

### kis-bridge 실행 방법
```bash
# 1. 한국투자증권 Open API 앱키 발급
#    https://apiportal.koreainvestment.com → 내 앱 → 앱 등록

# 2. .env에 추가
KIS_APP_KEY=<앱키>
KIS_APP_SECRET=<앱시크릿>
KIS_MOCK=false   # 모의투자 테스트 시 true

# 3. Docker로 실행 (docker-compose 포함)
docker-compose up kis-bridge

# 또는 직접 실행
pip install aiohttp websockets confluent-kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 python services/kis-bridge/main.py
```

| 항목 | 실전 | 모의투자 |
|------|------|----------|
| WebSocket URL | `wss://openapi.koreainvestment.com:21000` | `wss://openapiwss.kis.uat.koreainvestment.com:21000` |
| TR ID | `H0STCNT0` | `H0STCNS0` |
| 앱키 | 실전투자용 별도 발급 | 모의투자용 별도 발급 |

### 이상값 탐지 임계값 (장중 vs 일별)
| 모드 | `ANOMALY_THRESHOLD_PERCENT` | `INTRADAY_RECENT_MINUTES` | 설명 |
|------|---------------------------|--------------------------|------|
| 장중 1분봉 | `1.5` | `5` | 1분 내 1.5% 이상 변동, 최근 5분 bar만 처리 |
| 일별 (fallback) | `7.5` | `0` | 하루 7.5% 이상 변동, 5일 이내 데이터 처리 |

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

# 상시 실행 Deployment (1분봉 루프)
stock-collector     replicas: 1   # 60초 루프, yfinance 1분봉
kis-bridge          replicas: 1   # KIS WebSocket 상시 연결

# 자동 스케일링 (HPA)
ai-analyzer         CPU > 70% → Pod 자동 추가 (최대 5개)
api-server          요청 > 100rps → Pod 자동 추가
```

### CI/CD 흐름 (GitHub Actions → Harbor → ArgoCD → K8s)
```
코드 push (main)
    │
    ▼
GitHub Actions CI                     ← CI 담당
    ├── 테스트 실행
    ├── Docker 이미지 빌드 (서비스별 독립)
    │   ├── harbor.local/stock/api:$SHA
    │   ├── harbor.local/stock/frontend:$SHA
    │   ├── harbor.local/stock/stock-collector:$SHA
    │   ├── harbor.local/stock/kis-bridge:$SHA
    │   ├── harbor.local/stock/anomaly-detector:$SHA
    │   ├── harbor.local/stock/news-fetcher:$SHA
    │   ├── harbor.local/stock/ai-analyzer:$SHA
    │   └── harbor.local/stock/notifier:$SHA
    ├── Harbor (로컬 레지스트리)에 push   ← 이미지 저장소
    └── k8s/ 매니페스트의 이미지 태그 업데이트 후 커밋
            │
            ▼
    ArgoCD (GitOps)                   ← CD 담당
    ├── k8s/ 디렉토리 변경 감지 (Git 폴링/Webhook)
    ├── K8s 클러스터에 자동 Sync
    │
    ▼
    K8s Rolling Update → 다운타임 0
```

### Harbor 레지스트리 구성
```
harbor.local/                         # 로컬 Harbor 인스턴스
├── stock/                            # 프로젝트 네임스페이스
│   ├── api:latest / api:<git-sha>
│   ├── frontend:latest / frontend:<git-sha>
│   ├── stock-collector:latest
│   ├── kis-bridge:latest
│   ├── anomaly-detector:latest
│   ├── news-fetcher:latest
│   ├── ai-analyzer:latest
│   └── notifier:latest
```
- GitHub Actions에서 Harbor로 push 시 `HARBOR_URL`, `HARBOR_USER`, `HARBOR_PASSWORD` Secret 사용
- Harbor 내장 Trivy로 이미지 취약점 자동 스캔

### ArgoCD 앱 구성
```yaml
# argocd/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: stock-platform
  namespace: argocd
spec:
  source:
    repoURL: <git-repo-url>
    targetRevision: main
    path: k8s/
  destination:
    server: https://kubernetes.default.svc
    namespace: stock
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Prometheus + Grafana 모니터링 구성
```
Prometheus
├── kube-state-metrics          K8s 리소스 상태
├── node-exporter               노드 CPU/메모리/디스크
├── kafka-exporter              Kafka 토픽 lag, 처리량
└── FastAPI /metrics 엔드포인트  서비스별 요청 수, 지연시간

Grafana 대시보드
├── K8s 클러스터 개요
├── 서비스별 요청 현황 (api, ai-analyzer 등)
├── Kafka 파이프라인 처리량 및 지연 (lag)
└── 이상값 감지 현황 (DB 쿼리 기반 패널)
```

### Phase 4 완료 기준
- [x] K8s 매니페스트 작성 (`k8s/` 디렉토리: Deployment, Service, Ingress, HPA, ConfigMap, Secret)
- [x] GitHub Actions → Harbor로 서비스별 이미지 자동 빌드 + 푸시 (`.github/workflows/docker-build.yml`)
- [x] ArgoCD 설치 및 GitOps 파이프라인 연결 (`argocd/application.yaml`)
- [x] Prometheus + Grafana 모니터링 대시보드 (`monitoring/` 디렉토리)
- [x] Harbor 로컬 레지스트리 구성 문서화 (`SECRETS.md`)

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
    bar_timestamp   TEXT,                    -- 1분봉 정확한 시각 (YYYY-MM-DDTHH:MM:SS)
    return_pct      DECIMAL     NOT NULL,
    zscore          DECIMAL,
    close_price     DECIMAL,
    volume          BIGINT,
    direction       TEXT,                    -- '급등' or '급락'
    is_etf          BOOLEAN     DEFAULT FALSE, -- 섹터 ETF 여부
    event_type      TEXT,                    -- 'INDIVIDUAL', 'SECTOR', 'MARKET'
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
| Phase 3 (Kafka)        | ✅ 완료 | 안정적인 파이프라인, 확장성 확보 |
| Phase 4 (K8s + CI/CD)  | ✅ 완료 | GitHub Actions CI → Harbor → ArgoCD CD → K8s, Prometheus+Grafana 모니터링 |
