#!/bin/bash
# ============================================================
# Sealed Secrets 생성 스크립트
#
# 사전 조건:
#   1. sealed-secrets 컨트롤러가 클러스터에 설치되어 있어야 함
#      kubectl apply -f argocd/sealed-secrets-controller.yaml
#
#   2. kubeseal CLI 설치
#      https://github.com/bitnami-labs/sealed-secrets/releases
#      (Linux/Mac: brew install kubeseal)
#      (Windows: kubeseal.exe 다운로드 후 PATH에 추가)
#
#   3. 프로젝트 루트에 .env 파일 생성 (SECRETS.md 참고)
#
# 실행:
#   bash scripts/generate-sealed-secrets.sh
#
# 실행 후:
#   git add k8s/sealed-secrets/
#   git commit -m "chore: update sealed secrets"
#   git push
#   → ArgoCD가 감지하여 자동 배포
# ============================================================

set -euo pipefail

NAMESPACE="stock"
OUTPUT_DIR="k8s/sealed-secrets"
CONTROLLER_NS="kube-system"
CONTROLLER_NAME="sealed-secrets-controller"

# ── 색상 출력 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 사전 조건 확인 ──────────────────────────────────────────
command -v kubectl  >/dev/null 2>&1 || error "kubectl이 설치되지 않았습니다."
command -v kubeseal >/dev/null 2>&1 || error "kubeseal이 설치되지 않았습니다. https://github.com/bitnami-labs/sealed-secrets/releases"

info "Sealed Secrets 컨트롤러 연결 확인 중..."
kubectl -n "$CONTROLLER_NS" get deployment "$CONTROLLER_NAME" >/dev/null 2>&1 \
  || error "sealed-secrets-controller가 kube-system에 없습니다. 먼저 ArgoCD로 배포하세요:\n  kubectl apply -f argocd/sealed-secrets-controller.yaml"

# ── .env 로드 ──────────────────────────────────────────────
if [ ! -f ".env" ]; then
  error ".env 파일이 없습니다. SECRETS.md를 참고해서 루트에 .env를 생성하세요."
fi

info ".env 파일 로드 중..."
# export로 환경변수 설정 (주석, 빈 줄 제외)
set -a
# shellcheck disable=SC1091
source <(grep -v '^\s*#' .env | grep -v '^\s*$')
set +a

mkdir -p "$OUTPUT_DIR"

# kubeseal 기본 옵션
KUBESEAL_OPTS="--controller-namespace $CONTROLLER_NS --controller-name $CONTROLLER_NAME --format yaml"

# ── 필수 변수 확인 ──────────────────────────────────────────
required_vars=(GEMINI_API_KEY NEWS_API_KEY KIS_APP_KEY KIS_APP_SECRET HARBOR_URL HARBOR_USER HARBOR_PASSWORD)
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    warn "$var 가 .env에 없습니다. 해당 Secret은 건너뜁니다."
  fi
done

# ── 1. stock-api-secrets ────────────────────────────────────
if [ -n "${GEMINI_API_KEY:-}" ] && [ -n "${NEWS_API_KEY:-}" ]; then
  info "stock-api-secrets 생성 중..."
  kubectl create secret generic stock-api-secrets \
    -n "$NAMESPACE" \
    --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY}" \
    --from-literal=NEWS_API_KEY="${NEWS_API_KEY}" \
    --dry-run=client -o yaml \
    | kubeseal $KUBESEAL_OPTS > "$OUTPUT_DIR/stock-api-secrets.yaml"
  info "  → $OUTPUT_DIR/stock-api-secrets.yaml"
fi

# ── 2. stock-db-secret ─────────────────────────────────────
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-stock1234}"
info "stock-db-secret 생성 중..."
kubectl create secret generic stock-db-secret \
  -n "$NAMESPACE" \
  --from-literal=POSTGRES_USER=stock \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=POSTGRES_DB=stockdb \
  --dry-run=client -o yaml \
  | kubeseal $KUBESEAL_OPTS > "$OUTPUT_DIR/stock-db-secret.yaml"
info "  → $OUTPUT_DIR/stock-db-secret.yaml"

# ── 3. stock-kis-secret ────────────────────────────────────
if [ -n "${KIS_APP_KEY:-}" ] && [ -n "${KIS_APP_SECRET:-}" ]; then
  info "stock-kis-secret 생성 중..."
  kubectl create secret generic stock-kis-secret \
    -n "$NAMESPACE" \
    --from-literal=KIS_APP_KEY="${KIS_APP_KEY}" \
    --from-literal=KIS_APP_SECRET="${KIS_APP_SECRET}" \
    --from-literal=KIS_MOCK="${KIS_MOCK:-false}" \
    --dry-run=client -o yaml \
    | kubeseal $KUBESEAL_OPTS > "$OUTPUT_DIR/stock-kis-secret.yaml"
  info "  → $OUTPUT_DIR/stock-kis-secret.yaml"
fi

# ── 4. stock-notifier-secret ───────────────────────────────
if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
  info "stock-notifier-secret 생성 중..."
  kubectl create secret generic stock-notifier-secret \
    -n "$NAMESPACE" \
    --from-literal=SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL}" \
    --dry-run=client -o yaml \
    | kubeseal $KUBESEAL_OPTS > "$OUTPUT_DIR/stock-notifier-secret.yaml"
  info "  → $OUTPUT_DIR/stock-notifier-secret.yaml"
else
  warn "SLACK_WEBHOOK_URL 없음 — stock-notifier-secret 건너뜀 (Slack 알림 비활성)"
fi

# ── 5. harbor-pull-secret ──────────────────────────────────
if [ -n "${HARBOR_URL:-}" ] && [ -n "${HARBOR_USER:-}" ] && [ -n "${HARBOR_PASSWORD:-}" ]; then
  info "harbor-pull-secret 생성 중..."
  kubectl create secret docker-registry harbor-pull-secret \
    -n "$NAMESPACE" \
    --docker-server="${HARBOR_URL}" \
    --docker-username="${HARBOR_USER}" \
    --docker-password="${HARBOR_PASSWORD}" \
    --dry-run=client -o yaml \
    | kubeseal $KUBESEAL_OPTS > "$OUTPUT_DIR/harbor-pull-secret.yaml"
  info "  → $OUTPUT_DIR/harbor-pull-secret.yaml"
fi

# ── 완료 ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✅ SealedSecret 파일 생성 완료!${NC}"
echo ""
echo "다음 단계:"
echo "  git add k8s/sealed-secrets/"
echo "  git commit -m 'chore: update sealed secrets'"
echo "  git push"
echo "  → ArgoCD가 자동으로 감지해서 클러스터에 배포합니다."
echo ""
echo -e "${YELLOW}⚠️  .env 파일은 절대 git에 커밋하지 마세요!${NC}"
