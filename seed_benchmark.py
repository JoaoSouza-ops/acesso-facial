"""
seed_benchmark.py
=================
Popula o banco com N alunos sintéticos (padrão: 10.000) e mede a latência
da rota POST /api/v1/access/identify com o banco carregado.

Uso rápido:
    python seed_benchmark.py                    # popula 10k + benchmark
    python seed_benchmark.py --only-seed        # só popula
    python seed_benchmark.py --only-bench       # só mede (banco já populado)
    python seed_benchmark.py --total 500        # popula 500 alunos (teste rápido)
    python seed_benchmark.py --clean            # apaga alunos sintéticos antes de popular
"""

import argparse
import time
import sys
import statistics
import random
import string

import numpy as np

# ── Conexão com o banco (reutiliza exatamente o mesmo setup do projeto) ──────
# Execute este script a partir da raiz do projeto (mesma pasta do .env)
# ex: cd acesso-facial && python seed_benchmark.py
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # garante que .env é encontrado

from app.database import SessionLocal, engine
from app import models

# ── Constantes ────────────────────────────────────────────────────────────────
BATCH_SIZE      = 500      # alunos inseridos por commit (equilibra RAM e velocidade)
DEFAULT_TOTAL   = 10_000   # alunos sintéticos a criar
BENCH_ROUNDS    = 50       # consultas de benchmark por categoria
MATRICULA_PREFIX = "SEED"  # prefixo para identificar registros sintéticos

CURSOS = [
    "Ciência da Computação", "Engenharia de Software", "Sistemas de Informação",
    "Análise e Desenvolvimento de Sistemas", "Redes de Computadores",
    "Engenharia Elétrica", "Engenharia Civil", "Administração",
    "Direito", "Medicina", "Enfermagem", "Arquitetura",
]
TIPOS_VINCULO = ["GRADUACAO", "POS_GRADUACAO", "PROFESSOR", "FUNCIONARIO"]
TURNOS        = ["MANHA", "TARDE", "NOITE", "INTEGRAL"]

NOMES = [
    "Ana", "Bruno", "Carlos", "Diana", "Eduardo", "Fernanda", "Gabriel",
    "Helena", "Igor", "Juliana", "Kevin", "Laura", "Marcos", "Natália",
    "Otávio", "Paula", "Rafael", "Sabrina", "Thiago", "Ursula",
    "Vinícius", "Wendy", "Xavier", "Yasmin", "Zeca",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa",
    "Ferreira", "Rodrigues", "Almeida", "Nascimento", "Carvalho", "Mendes",
    "Ribeiro", "Gomes", "Martins", "Barbosa", "Rocha", "Araújo", "Moreira",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def gerar_vetor() -> list[float]:
    """Gera um vetor L2-normalizado de 128 dimensões (distribução gaussiana)."""
    v = np.random.randn(128).astype(np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


def gerar_matricula(i: int) -> str:
    sufixo = "".join(random.choices(string.ascii_uppercase, k=3))
    return f"{MATRICULA_PREFIX}{i:07d}{sufixo}"[:20]


def gerar_nome() -> str:
    return f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"


def barra(atual: int, total: int, largura: int = 40) -> str:
    pct   = atual / total
    cheio = int(largura * pct)
    return f"[{'█' * cheio}{'░' * (largura - cheio)}] {atual:>6}/{total} ({pct:.0%})"


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed(total: int, clean: bool) -> None:
    db = SessionLocal()
    try:
        if clean:
            print("🗑  Removendo registros sintéticos anteriores...")
            deleted = db.query(models.Aluno)\
                .filter(models.Aluno.matricula.like(f"{MATRICULA_PREFIX}%"))\
                .delete(synchronize_session=False)
            db.commit()
            print(f"   {deleted} registros removidos.\n")

        # Quantos já existem para não recriar
        ja_existem = db.query(models.Aluno)\
            .filter(models.Aluno.matricula.like(f"{MATRICULA_PREFIX}%"))\
            .count()

        restantes = total - ja_existem
        if restantes <= 0:
            print(f"✅ Banco já tem {ja_existem} alunos sintéticos. Nada a fazer.")
            return

        print(f"📥 Inserindo {restantes:,} alunos em batches de {BATCH_SIZE}...\n")
        t0 = time.perf_counter()

        inseridos = 0
        offset = ja_existem  # evita colisão de matrícula
        batch: list[models.Aluno] = []

        for i in range(restantes):
            idx = offset + i
            batch.append(models.Aluno(
                matricula    = gerar_matricula(idx),
                nome_completo= gerar_nome(),
                curso        = random.choice(CURSOS),
                tipo_vinculo = random.choice(TIPOS_VINCULO),
                turno        = random.choice(TURNOS),
                status_acesso= "ATIVO",
                vetor_128d   = gerar_vetor(),
            ))

            if len(batch) >= BATCH_SIZE:
                db.bulk_save_objects(batch)
                db.commit()
                inseridos += len(batch)
                batch = []
                elapsed = time.perf_counter() - t0
                taxa = inseridos / elapsed
                print(f"\r  {barra(inseridos, restantes)}  {taxa:,.0f} alunos/s", end="", flush=True)

        # Flush do último batch parcial
        if batch:
            db.bulk_save_objects(batch)
            db.commit()
            inseridos += len(batch)

        elapsed = time.perf_counter() - t0
        print(f"\r  {barra(inseridos, restantes)}  ✓ concluído")
        print(f"\n✅ {inseridos:,} alunos inseridos em {elapsed:.1f}s  "
              f"({inseridos / elapsed:,.0f} registros/s)\n")

    finally:
        db.close()


# ── Benchmark ─────────────────────────────────────────────────────────────────

def bench(rounds: int) -> None:
    """
    Mede a latência da query pgvector que o /identify usa internamente.
    Roda 3 categorias:
      - HIT  : vetor clonado de um aluno real (deve ser LIBERADO, distância ~0)
      - NEAR : vetor real + ruído leve       (zona de incerteza, dist ~0.3–0.5)
      - MISS : vetor aleatório               (desconhecido, dist > 0.6)
    """
    db = SessionLocal()
    try:
        total_alunos = db.query(models.Aluno).count()
        print(f"📊 Banco atual: {total_alunos:,} alunos")
        print(f"🔬 Rodando benchmark — {rounds} consultas por categoria...\n")

        # Pega uma amostra de alunos reais para usar como base dos vetores
        amostra = db.query(models.Aluno.vetor_128d)\
            .order_by(models.Aluno.id_aluno)\
            .limit(rounds * 2)\
            .all()

        if len(amostra) < rounds:
            print("⚠  Poucos alunos no banco para o número de rounds solicitado. "
                  "Reduza --bench-rounds ou rode --only-seed primeiro.")
            return

        def medir(categoria: str, vetores: list) -> dict:
            latencias = []
            for v in vetores[:rounds]:
                t0 = time.perf_counter()
                db.query(
                    models.Aluno,
                    models.Aluno.vetor_128d.l2_distance(v).label("distancia")
                ).order_by("distancia").first()
                latencias.append((time.perf_counter() - t0) * 1000)

            p50  = statistics.median(latencias)
            p95  = sorted(latencias)[int(len(latencias) * 0.95)]
            p99  = sorted(latencias)[int(len(latencias) * 0.99)]
            minv = min(latencias)
            maxv = max(latencias)

            status = "🟢" if p95 < 50 else ("🟡" if p95 < 150 else "🔴")
            print(f"  {status}  {categoria:<8}  "
                  f"p50={p50:6.1f}ms  p95={p95:6.1f}ms  p99={p99:6.1f}ms  "
                  f"min={minv:5.1f}ms  max={maxv:5.1f}ms")
            return {"categoria": categoria, "p50": p50, "p95": p95, "p99": p99}

        # ── HIT: cópia exata de um vetor real ──
        vetores_hit = [list(row[0]) for row in amostra[:rounds]]

        # ── NEAR: vetor real + ruído gaussiano pequeno (simula face parecida) ──
        vetores_near = []
        for row in amostra[rounds:rounds * 2]:
            v = np.array(row[0], dtype=np.float32)
            ruido = np.random.randn(128).astype(np.float32) * 0.15
            v = v + ruido
            v /= np.linalg.norm(v)
            vetores_near.append(v.tolist())

        # ── MISS: vetor completamente aleatório (desconhecido) ──
        vetores_miss = [gerar_vetor() for _ in range(rounds)]

        print(f"  {'Categoria':<10}  {'p50':>8}  {'p95':>8}  {'p99':>8}  "
              f"{'min':>7}  {'max':>7}")
        print("  " + "─" * 65)

        resultados = []
        resultados.append(medir("HIT",  vetores_hit))
        resultados.append(medir("NEAR", vetores_near))
        resultados.append(medir("MISS", vetores_miss))

        print()
        p95_max = max(r["p95"] for r in resultados)
        if p95_max < 50:
            print("✅ Performance excelente — p95 < 50ms em todos os cenários.")
        elif p95_max < 150:
            print("🟡 Performance aceitável — considere criar um índice HNSW no pgvector:")
            print("   CREATE INDEX ON alunos USING hnsw (vetor_128d vector_l2_ops);")
        else:
            print("🔴 Latência alta — índice HNSW obrigatório:")
            print("   CREATE INDEX ON alunos USING hnsw (vetor_128d vector_l2_ops);")
            print("   Após criar o índice, rode novamente: python seed_benchmark.py --only-bench")

        # Dica sobre o índice
        print()
        print("💡 Dica: para verificar se o índice pgvector já existe no seu banco:")
        print("   SELECT indexname FROM pg_indexes WHERE tablename = 'alunos';")

    finally:
        db.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed 10k alunos sintéticos + benchmark da rota identify"
    )
    parser.add_argument("--total",       type=int,  default=DEFAULT_TOTAL,
                        help=f"Total de alunos a inserir (padrão: {DEFAULT_TOTAL})")
    parser.add_argument("--batch-size",  type=int,  default=BATCH_SIZE,
                        help=f"Alunos por commit (padrão: {BATCH_SIZE})")
    parser.add_argument("--bench-rounds",type=int,  default=BENCH_ROUNDS,
                        help=f"Consultas de benchmark por categoria (padrão: {BENCH_ROUNDS})")
    parser.add_argument("--only-seed",   action="store_true",
                        help="Só popula o banco, sem benchmark")
    parser.add_argument("--only-bench",  action="store_true",
                        help="Só roda o benchmark, sem popular")
    parser.add_argument("--clean",       action="store_true",
                        help="Remove alunos sintéticos existentes antes de popular")
    args = parser.parse_args()

    print("=" * 60)
    print("  seed_benchmark.py — Sistema de Acesso Facial")
    print("=" * 60)
    print()

    if not args.only_bench:
        seed(total=args.total, clean=args.clean)

    if not args.only_seed:
        bench(rounds=args.bench_rounds)


if __name__ == "__main__":
    main()