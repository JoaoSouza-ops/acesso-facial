#!/usr/bin/env bash
# =============================================================================
# run_stress_test.sh — Execução em estágios do teste de estresse
# Sistema de Acesso Facial · ExpoTech 2026
#
# Uso:
#   chmod +x run_stress_test.sh
#   ./run_stress_test.sh
#
# Variáveis de ambiente opcionais (override dos defaults do locustfile.py):
#   API_KEY_ENROLL   API_KEY_DEVICE   API_KEY_ADMIN
#   DEVICE_MAC       FOTO_VERIFY_PATH
# =============================================================================

set -euo pipefail

HOST="http://localhost:8000"
LOCUST_FILE="tests/locustfile.py"
RELATORIO_DIR="stress_reports"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$RELATORIO_DIR"

# Verifica se locust está instalado
if ! command -v locust &>/dev/null; then
    echo "❌  Locust não encontrado. Instale com:"
    echo "    pip install locust"
    exit 1
fi

# Verifica se a API está respondendo antes de estressar
echo "🔍  Verificando se a API está no ar em $HOST..."
if ! curl -sf "$HOST/api/v1/healthz" > /dev/null; then
    echo "❌  API não está respondendo em $HOST/api/v1/healthz"
    echo "    Suba o servidor com: uvicorn app.main:app --host 0.0.0.0 --port 8000"
    exit 1
fi
echo "✅  API online."
echo ""

# =============================================================================
# Função auxiliar para rodar um estágio
# =============================================================================
rodar_estagio() {
    local nome="$1"
    local usuarios="$2"
    local spawn_rate="$3"
    local duracao="$4"
    local arquivo_html="$RELATORIO_DIR/${TIMESTAMP}_${nome}.html"
    local arquivo_csv="$RELATORIO_DIR/${TIMESTAMP}_${nome}"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Estágio: $nome"
    echo "  Usuários simultâneos : $usuarios"
    echo "  Spawn rate           : $spawn_rate usuários/s"
    echo "  Duração              : $duracao"
    echo "  Relatório HTML       : $arquivo_html"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    locust \
        -f "$LOCUST_FILE" \
        --headless \
        --host "$HOST" \
        --users "$usuarios" \
        --spawn-rate "$spawn_rate" \
        --run-time "$duracao" \
        --html "$arquivo_html" \
        --csv "$arquivo_csv" \
        2>&1 | tee "$RELATORIO_DIR/${TIMESTAMP}_${nome}.log"

    echo ""
    echo "  📄 Relatório salvo: $arquivo_html"
    echo ""

    # Pausa entre estágios para deixar o servidor se recuperar
    if [[ "$nome" != "estagio_4_pico" ]]; then
        echo "  ⏸  Aguardando 10s antes do próximo estágio..."
        sleep 10
    fi
}

# =============================================================================
# Plano de carga progressiva
#
# Estágio 1 — Aquecimento (warm-up)
#   25 usuários · ~150 req/min esperados
#   Objetivo: confirmar que a API funciona antes de escalar
#
# Estágio 2 — Carga moderada
#   50 usuários · ~300 req/min esperados
#   Objetivo: baseline de latência e throughput
#
# Estágio 3 — Carga alvo
#   100 usuários · ~500–600 req/min esperados
#   Objetivo: PROVAR ≥ 500 req/min com p95 < 500ms
#
# Estágio 4 — Pico / stress
#   200 usuários · ~900–1200 req/min esperados
#   Objetivo: encontrar o ponto de saturação da API
# =============================================================================

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   TESTE DE ESTRESSE — SISTEMA DE ACESSO FACIAL              ║"
echo "║   Meta: ≥ 500 req/min · p95 < 500ms · falhas < 1%          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

rodar_estagio "estagio_1_warmup"    25  5  "60s"
rodar_estagio "estagio_2_moderado"  50  10 "60s"
rodar_estagio "estagio_3_alvo"     100  20 "90s"
rodar_estagio "estagio_4_pico"     200  25 "60s"

# =============================================================================
# Consolidação final
# =============================================================================
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   TESTE CONCLUÍDO                                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Todos os relatórios estão em: ./$RELATORIO_DIR/"
echo ""
echo "  Arquivos gerados:"
ls -1 "$RELATORIO_DIR/" | grep "$TIMESTAMP" | sed 's/^/    /'
echo ""
echo "  Para abrir o relatório do estágio 3 (carga alvo):"
echo "    open $RELATORIO_DIR/${TIMESTAMP}_estagio_3_alvo.html"
echo ""
echo "  Para analisar os CSVs no Python:"
echo "    python analise_resultados.py $RELATORIO_DIR/${TIMESTAMP}_estagio_3_alvo_stats.csv"
echo ""