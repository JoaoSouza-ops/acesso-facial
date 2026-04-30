"""
analise_resultados.py — Análise dos CSVs gerados pelo Locust
============================================================
Uso:
    python analise_resultados.py stress_reports/<timestamp>_estagio_3_alvo_stats.csv

Gera:
    • Tabela de métricas por endpoint no terminal
    • Critério de aprovação/reprovação documentado
"""

import sys
import csv
from pathlib import Path


CRITERIOS = {
    "rpm_minimo":     500,    # req/min mínimo para aprovação
    "p95_maximo_ms":  500,    # latência p95 máxima (ms)
    "falha_max_pct":  1.0,    # taxa de falha máxima (%)
}


def ler_csv(caminho: str) -> list[dict]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def formatar_linha(nome: str, dados: dict) -> str:
    reqs      = int(dados.get("Request Count", 0))
    falhas    = int(dados.get("Failure Count", 0))
    falha_pct = (falhas / reqs * 100) if reqs > 0 else 0.0
    p50       = float(dados.get("50%", 0))
    p95       = float(dados.get("95%", 0))
    p99       = float(dados.get("99%", 0))
    rps       = float(dados.get("Requests/s", 0))
    rpm       = rps * 60

    aprovado_rpm   = "✅" if rpm  >= CRITERIOS["rpm_minimo"]     else "❌"
    aprovado_p95   = "✅" if p95  <= CRITERIOS["p95_maximo_ms"]  else "❌"
    aprovado_falha = "✅" if falha_pct <= CRITERIOS["falha_max_pct"] else "❌"

    return (
        f"  {nome:<35} "
        f"reqs={reqs:>6}  "
        f"falhas={falhas:>4} ({falha_pct:>5.1f}%) {aprovado_falha}  "
        f"p50={p50:>5.0f}ms  "
        f"p95={p95:>5.0f}ms {aprovado_p95}  "
        f"p99={p99:>5.0f}ms  "
        f"rpm={rpm:>6.0f} {aprovado_rpm}"
    )


def main():
    if len(sys.argv) < 2:
        print("Uso: python analise_resultados.py <arquivo_stats.csv>")
        sys.exit(1)

    caminho = sys.argv[1]
    if not Path(caminho).exists():
        print(f"Arquivo não encontrado: {caminho}")
        sys.exit(1)

    linhas = ler_csv(caminho)

    print()
    print("=" * 110)
    print("  ANÁLISE DE RESULTADOS — SISTEMA DE ACESSO FACIAL")
    print(f"  Arquivo: {caminho}")
    print("=" * 110)
    print(f"  {'Endpoint':<35} {'Reqs':>6}  {'Falhas':>14}   "
          f"{'p50':>8}  {'p95':>8}   {'p99':>8}  {'req/min':>10}")
    print("-" * 110)

    agregado = None
    for linha in linhas:
        nome = linha.get("Name", "")
        if nome == "Aggregated":
            agregado = linha
            continue
        print(formatar_linha(nome, linha))

    print("-" * 110)
    if agregado:
        print(formatar_linha("TOTAL AGREGADO", agregado))
    print("=" * 110)

    # Critério de aprovação consolidado
    print()
    print("  CRITÉRIOS DE APROVAÇÃO")
    print(f"  {'Critério':<40} {'Mínimo/Máximo':>15}  {'Resultado':>12}  Status")
    print("  " + "-" * 80)

    if agregado:
        rps       = float(agregado.get("Requests/s", 0))
        rpm       = rps * 60
        p95       = float(agregado.get("95%", 0))
        reqs      = int(agregado.get("Request Count", 0))
        falhas    = int(agregado.get("Failure Count", 0))
        falha_pct = (falhas / reqs * 100) if reqs > 0 else 0.0

        criterios = [
            ("Throughput mínimo",   f"≥ {CRITERIOS['rpm_minimo']} req/min",
             f"{rpm:.0f} req/min",   rpm  >= CRITERIOS["rpm_minimo"]),
            ("Latência p95 máxima", f"≤ {CRITERIOS['p95_maximo_ms']}ms",
             f"{p95:.0f}ms",         p95  <= CRITERIOS["p95_maximo_ms"]),
            ("Taxa de falha máxima",f"< {CRITERIOS['falha_max_pct']}%",
             f"{falha_pct:.2f}%",    falha_pct <= CRITERIOS["falha_max_pct"]),
        ]

        todos_aprovados = True
        for nome_c, limite, resultado, ok in criterios:
            status = "✅ APROVADO" if ok else "❌ REPROVADO"
            if not ok:
                todos_aprovados = False
            print(f"  {nome_c:<40} {limite:>15}  {resultado:>12}  {status}")

        print()
        if todos_aprovados:
            print("  🎉  RESULTADO FINAL: APROVADO")
            print("       A API suporta ≥ 500 req/min com p95 < 500ms e falhas < 1%")
        else:
            print("  ⚠️   RESULTADO FINAL: REPROVADO — revise os critérios acima")
    else:
        print("  (linha Aggregated não encontrada no CSV)")

    print("=" * 110)
    print()


if __name__ == "__main__":
    main()