# 주식 이상값 AI 분석 플랫폼 - 아키텍처 & 개발 로드맵

---

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 기술 스택](#2-전체-기술-스택)
3. [Phase 1 - FastAPI 백엔드](#phase-1--fastapi-백엔드-12주)
4. [Phase 2 - 프론트엔드 대시보드](#phase-2--프론트엔드-대시보드-24주)
5. [Phase 3 - Kafka 파이프라인](#phase-3--kafka-파이프라인-12개월)
6. [Phase 4 - Docker & Kubernetes](#phase-4--docker--kubernetes-23개월)
7. [최종 아키텍처 다이어그램](#7-최종-아키텍처-다이어그램)
8. [DB 스키마 설계](#8-db-스키마-설계)
9. [API 명세](#9-api-명세)

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

## 2. 전체 기술 스택

### Backend
| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| API 서버 | **FastAPI** | Python 기반, 비동기 지원, 자동 Swagger 문서 |
| 메시지 큐 | **Apache Kafka** | 대용량 스트림, 서비스 간 완전한 비동기 분리 |
| 시계열 DB | **TimescaleDB** (PostgreSQL 확장) | 주가처럼 시간 기반 데이터 조회에 최적화 |
| 캐시 | **Redis** | API 결과 캐싱, 실시간 알림 큐 |
| 문서 저장 | **MongoDB** | AI 분석 텍스트, 뉴스 원문 등 비정형 데이터 |
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
| 로그 | **ELK Stack** (Elasticsearch + Logstash + Kibana) | 분산 로그 수집/분석 |

---

## Phase 1 — FastAPI 백엔드 (1~2주)

### 목표
현재 스크립트를 API 서버로 전환. DB에 결과를 저장하고 외부에서 조회 가능하게 만들기.

### 디렉토리 구조
```
project/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── routers/
│   │   ├── anomalies.py     # GET /anomalies
│   │   ├── sectors.py       # GET /sectors/trending
│   │   └── analysis.py      # POST /analyze
│   ├── services/
│   │   ├── stock_fetcher.py  # (현재 코드 재사용)
│   │   ├── news_fetcher.py   # (현재 코드 재사용)
│   │   └── ai_analyzer.py    # (현재 코드 재사용)
│   ├── models/
│   │   ├── anomaly.py        # Pydantic 모델
│   │   └── sector.py
│   ├── db/
│   │   ├── connection.py     # DB 연결 (asyncpg)
│   │   └── queries.py        # SQL 쿼리
│   └── scheduler.py          # APScheduler → 주기적 수집
├── stock_categories.py       # (현재 코드 그대로 사용)
└── requirements.txt
```

### 핵심 API 엔드포인트
```
GET  /anomalies                    최근 이상값 목록 (페이징)
GET  /anomalies/{ticker}           특정 종목 이상값 이력
GET  /sectors/trending             섹터별 관심도 트렌드
GET  /sectors/{name}/anomalies     섹터 내 이상값 목록
POST /analyze/trigger              수동으로 전체 분석 실행
WS   /ws/live                      실시간 이상값 알림 (WebSocket)
```

### DB: TimescaleDB 선택 이유
```sql
-- 일반 PostgreSQL 쿼리로 쓰면서 시계열 최적화 자동 적용
-- 예: "최근 7일간 반도체 섹터 급등 종목"
SELECT ticker, date, return_pct
FROM anomalies
WHERE sector = '반도체 (Semiconductor)'
  AND date > NOW() - INTERVAL '7 days'
  AND return_pct > 0
ORDER BY return_pct DESC;
-- TimescaleDB가 날짜 기반 파티셔닝으로 이 쿼리를 매우 빠르게 실행
```

### Phase 1 완료 기준
- [ ] FastAPI 서버 정상 실행
- [ ] `/anomalies` API 응답 확인
- [ ] TimescaleDB에 이상값 자동 저장
- [ ] Swagger UI (`/docs`)에서 API 테스트 가능
- [ ] APScheduler로 60분마다 자동 수집

---

## Phase 2 — 프론트엔드 대시보드 (2~4주)

### 목표
브라우저에서 이상값 대시보드 확인. 실시간 알림 수신.

### 화면 구성
```
┌─────────────────────────────────────────────────────┐
│  HEADER: 마지막 업데이트 시각 / 실시간 연결 상태      │
├───────────────────┬─────────────────────────────────┤
│  섹터별 히트맵     │  오늘의 이상값 목록              │
│  (어느 섹터가      │  ┌──────────────────────────┐   │
│   뜨거운지 색상)   │  │ NVDA  +12.3%  [SECTOR]   │   │
│                   │  │ 반도체 AI 투자 급증 원인... │   │
│                   │  ├──────────────────────────┤   │
│                   │  │ POSCO -8.1%  [INDIVIDUAL] │   │
│                   │  │ 철강 관세 부과 우려...     │   │
├───────────────────┴─────────────────────────────────┤
│  선택 종목 주가 차트 (30일) + 이상값 마커 표시        │
├─────────────────────────────────────────────────────┤
│  AI 분석 리포트 패널 (한국어 / 영어 탭 전환)          │
└─────────────────────────────────────────────────────┘
```

### 실시간 알림 흐름
```
[FastAPI 백엔드]                    [Next.js 프론트]
     │                                     │
     │  이상값 감지                         │
     │──── WebSocket 메시지 ──────────────→ │
     │  {ticker, return_pct, direction}    │
     │                                     │  브라우저 알림 팝업
     │                                     │  + 목록 자동 업데이트
```

### Phase 2 완료 기준
- [ ] 섹터 히트맵 렌더링
- [ ] 이상값 목록 실시간 업데이트
- [ ] 종목 클릭 → 상세 차트 + AI 분석 표시
- [ ] 한국어 / 영어 탭 전환

---

## Phase 3 — Kafka 파이프라인 (1~2개월)

### 목표
데이터 수집 → 분석 → 저장 → 알림을 완전히 비동기 파이프라인으로 분리.
한 단계가 느려져도 전체 시스템에 영향 없음.

### Kafka Topic 설계
```
stock.raw.us        미국 주가 원시 데이터 (yfinance)
stock.raw.kr        한국 주가 원시 데이터 (pykrx)
anomaly.detected    이상값 감지 결과
news.fetched        뉴스 수집 완료 이벤트
analysis.completed  AI 분석 완료 결과
notification.queue  알림 발송 큐 (슬랙/이메일)
```

### 서비스별 역할
```
[stock-collector]   →  stock.raw.us / stock.raw.kr 에 발행
[anomaly-detector]  ←  stock.raw 구독  →  anomaly.detected 발행
[news-fetcher]      ←  anomaly.detected 구독  →  news.fetched 발행
[ai-analyzer]       ←  news.fetched 구독  →  analysis.completed 발행
[db-writer]         ←  analysis.completed 구독  →  DB 저장
[notifier]          ←  analysis.completed 구독  →  슬랙/이메일 발송
```

### 비동기 분리의 장점
```
Before (현재):  수집 → 분석 → 저장 → 알림  (순차, 앞이 막히면 전체 멈춤)
After  (Kafka): 각 단계가 독립 실행          (한 단계 지연이 다른 단계에 무관)

예: AI 분석이 Gemini 속도 제한으로 느려져도
    수집과 DB 저장은 계속 정상 동작
```

### Phase 3 완료 기준
- [ ] Kafka 컨테이너 실행 (Zookeeper 포함)
- [ ] 5개 서비스가 각자 Topic 구독/발행
- [ ] 장애 시나리오 테스트 (AI 서비스 중단 → 나머지 정상 동작 확인)

---

## Phase 4 — Docker & Kubernetes (2~3개월)

### Docker: 서비스별 이미지 분리
```
stock-collector     Python 3.11 + yfinance + pykrx
anomaly-detector    Python 3.11 + pandas + numpy
news-fetcher        Python 3.11 + feedparser + bs4
ai-analyzer         Python 3.11 + google-generativeai
db-writer           Python 3.11 + asyncpg
notifier            Python 3.11 + slack-sdk
api-server          Python 3.11 + FastAPI + uvicorn
frontend            Node.js 20 + Next.js
```

### Kubernetes 리소스 구성
```yaml
# 상태 없는 서비스 (Deployment)
api-server          replicas: 3   # 로드밸런싱
ai-analyzer         replicas: 2   # Gemini API 병렬 처리
anomaly-detector    replicas: 2
frontend            replicas: 2

# 상태 있는 서비스 (StatefulSet)
kafka               replicas: 3   # 브로커 3개 클러스터
timescaledb         replicas: 1   # Primary + 1 Replica
mongodb             replicas: 3   # ReplicaSet
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
    ├── Docker 이미지 빌드
    └── Docker Hub에 push (tag: git SHA)
            │
            ▼
    kubectl set image 배포
            │
            ▼
    K8s Rolling Update (구 Pod 하나씩 교체)
    → 다운타임 0
```

### Phase 4 완료 기준
- [ ] 전체 서비스 Dockerfile 작성
- [ ] docker-compose.yml로 로컬 통합 테스트
- [ ] K8s 매니페스트 작성 (Deployment, Service, Ingress)
- [ ] GitHub Actions → 자동 이미지 빌드 + 배포
- [ ] Prometheus + Grafana 모니터링 대시보드

---

## 7. 최종 아키텍처 다이어그램

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
              │Anomaly  │ │News   │ │AI       │ │Notifier  │
              │Detector │ │Fetcher│ │Analyzer │ │슬랙/메일  │
              │(Pod × 2)│ │(Pod×2)│ │(Pod × 2)│ │(Pod × 1) │
              └────┬────┘ └───────┘ └────┬────┘ └──────────┘
                   │                     │
              ┌────▼─────────────────────▼──────────────────┐
              │                Databases                     │
              │                                              │
              │  ┌──────────────┐  ┌───────┐  ┌──────────┐  │
              │  │ TimescaleDB  │  │ Redis │  │ MongoDB  │  │
              │  │ (주가/이상값) │  │(캐시) │  │(분석텍스트)│ │
              │  └──────────────┘  └───────┘  └──────────┘  │
              └──────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Monitoring Stack   │
              │  Prometheus+Grafana │
              └─────────────────────┘
```

---

## 8. DB 스키마 설계

### TimescaleDB (주가 & 이상값)
```sql
-- 주가 원시 데이터 (Hypertable: 시계열 최적화)
CREATE TABLE stock_prices (
    time        TIMESTAMPTZ NOT NULL,
    ticker      TEXT        NOT NULL,
    open        DECIMAL,
    high        DECIMAL,
    low         DECIMAL,
    close       DECIMAL     NOT NULL,
    volume      BIGINT,
    market      TEXT        -- 'US' or 'KR'
);
SELECT create_hypertable('stock_prices', 'time');

-- 이상값 감지 결과
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

-- AI 분석 결과 (MongoDB에 저장하고 여기선 참조 ID만)
CREATE TABLE analysis_results (
    id          SERIAL PRIMARY KEY,
    anomaly_id  INT REFERENCES anomalies(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    mongo_id    TEXT        -- MongoDB document ID
);
```

### MongoDB (AI 분석 텍스트 & 뉴스)
```javascript
// analysis_results collection
{
  _id: ObjectId,
  anomaly_id: 123,
  ticker: "NVDA",
  sector: "반도체 (Semiconductor)",
  event_type: "SECTOR",
  analysis_ko: "**원인 분석:**\n엔비디아의 ...",
  analysis_en: "**Root Cause Analysis:**\nNVIDIA's ...",
  news_en: [
    { title: "...", source: "Reuters", url: "...", published_at: "..." }
  ],
  news_kr: [
    { title: "...", source: "네이버뉴스", url: "...", published_at: "..." }
  ],
  created_at: ISODate
}
```

---

## 9. API 명세

```
GET  /api/v1/anomalies
     Query: ?days=7&sector=반도체&event_type=SECTOR&limit=20
     Response: [{ ticker, date, return_pct, direction, event_type, sector }]

GET  /api/v1/anomalies/{ticker}/history
     Query: ?days=30
     Response: [{ date, return_pct, zscore, event_type, analysis_id }]

GET  /api/v1/anomalies/{anomaly_id}/analysis
     Response: { analysis_ko, analysis_en, news_en, news_kr }

GET  /api/v1/sectors/trending
     Query: ?days=7
     Response: [{ sector, anomaly_count, avg_return, hot_tickers }]

POST /api/v1/analyze/trigger
     Body: { force: true }
     Response: { job_id, status: "queued" }

GET  /api/v1/jobs/{job_id}
     Response: { status, started_at, completed_at, anomaly_count }

WS   /ws/live
     Server → Client: { type: "anomaly", ticker, return_pct, sector, event_type }
```

---

## 개발 우선순위 요약

| 단계 | 기간 | 핵심 가치 |
|------|------|-----------|
| Phase 1 (FastAPI + DB) | 1~2주 | 결과가 DB에 쌓이고 API로 조회 가능 |
| Phase 2 (Frontend)     | 2~4주 | 시각적 대시보드, 실시간 알림 |
| Phase 3 (Kafka)        | 1~2개월 | 안정적인 파이프라인, 확장성 확보 |
| Phase 4 (K8s)          | 2~3개월 | 프로덕션 수준 운영, 자동 스케일링 |

> Phase 1 → 2 순서로 진행하면서 실제로 써보고 필요할 때 Phase 3, 4로 확장 권장.
> Kafka와 K8s는 트래픽이 많아지거나 팀이 생길 때 도입해도 늦지 않음.
