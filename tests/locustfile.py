"""
locustfile.py — Teste de Estresse · Sistema de Acesso Facial
=============================================================
Cobre 4 endpoints:
  • GET  /api/v1/healthz          → liveness probe
  • GET  /api/v1/readyz           → readiness probe (banco online)
  • POST /api/v1/access/enroll    → cadastro biométrico
  • POST /api/v1/access/verify    → verificação facial (fluxo principal)

Meta: provar ≥ 500 req/min sem degradação de latência (p95 < 500ms).

Execução rápida (modo headless):
  locust -f locustfile.py --headless -u 100 -r 10 --run-time 60s \
         --html relatorio_stress.html --host http://localhost:8000

Interface web (acompanhar ao vivo):
  locust -f locustfile.py --host http://localhost:8000
  → abrir http://localhost:8089
"""

import io
import os
import random
import string
import struct
import time

from locust import HttpUser, TaskSet, between, events, tag, task

# ---------------------------------------------------------------------------
# Configuração — ajuste conforme seu .env
# ---------------------------------------------------------------------------
API_KEY_ENROLL = os.getenv("API_KEY_ENROLL", "chave_secreta_enroll_123")
API_KEY_DEVICE = os.getenv("API_KEY_DEVICE", "hub-dev-device-chave-secreta-001")
API_KEY_ADMIN  = os.getenv("API_KEY_ADMIN",  "chave_secreta_admin_123")
MAC_ADRESS    = os.getenv("MAC_DEVICE",    "00:11:22:33:44:55")


# MAC address fixo que deve existir na tabela Dispositivos do seu banco.
# Rode seed_db.py e copie o mac do dispositivo criado.

# ---------------------------------------------------------------------------
# Helpers — geração de dados sintéticos sem depender de arquivos externos
# ---------------------------------------------------------------------------

def _jpeg_sintetico(width: int = 64, height: int = 64) -> bytes:
    """
    Gera um JPEG mínimo válido via bytes brutos.
    NÃO contém rosto real — o backend retornará 422 (LowQualityImageError
    ou sem rosto detectado). Isso é intencional: queremos estressar o
    pipeline de validação, não cadastrar dados reais.
    Para testar o caminho feliz (200 OK), substitua por uma foto real
    usando _jpeg_de_arquivo() abaixo.
    """
    try:
        import numpy as np
        from PIL import Image

        # Imagem RGB com ruído aleatório (simula variação entre requests)
        arr = np.random.randint(100, 200, (height, width, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        # Fallback: JPEG header mínimo (2 KB de zeros) — suficiente para
        # testar o parsing da API sem Pillow/numpy instalados
        header = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
            0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
        ])
        return header + bytes(2000)


def _jpeg_de_arquivo(caminho: str) -> bytes:
    """
    Carrega um JPEG real do disco — use para testar o caminho feliz (200 OK).
    Exemplo: coloque uma foto cadastrada em tests/fixtures/rosto_joao.jpg
    e aponte FOTO_VERIFY_PATH para esse arquivo.
    """
    with open(caminho, "rb") as f:
        return f.read()


def _matricula_aleatoria() -> str:
    ano = random.randint(2020, 2025)
    seq = random.randint(100000, 999999)
    return f"{ano}{seq}"


def _nome_aleatorio() -> str:
    nomes = ["Ana", "Bruno", "Carlos", "Diana", "Eduardo", "Fernanda",
             "Gabriel", "Helena", "Igor", "Julia"]
    sobrenomes = ["Silva", "Santos", "Oliveira", "Souza", "Lima",
                  "Pereira", "Costa", "Ferreira", "Rodrigues", "Almeida"]
    return f"{random.choice(nomes)} {random.choice(sobrenomes)}"


# Caminho opcional para foto real usada no /verify (caminho feliz)

FOTO_VERIFY_PATH = "tests/fixtures/foto_esp32.jpg"


# ---------------------------------------------------------------------------
# TaskSets — agrupa tasks por perfil de usuário
# ---------------------------------------------------------------------------

class TarefasMonitoramento(TaskSet):
    """
    Simula o dashboard e o healthcheck do load balancer.
    Alta frequência, payloads pequenos.
    """

    @tag("healthz")
    @task(5)   # peso 5 — chamado com mais frequência
    def healthz(self):
        with self.client.get(
            "/api/v1/healthz",
            name="GET /healthz",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Esperado 200, recebido {resp.status_code}")

    @tag("readyz")
    @task(2)
    def readyz(self):
        with self.client.get(
            "/api/v1/readyz",
            name="GET /readyz",
            catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                # Banco offline — registra como falha de infraestrutura
                resp.failure("Banco offline (503)")
            else:
                resp.failure(f"Inesperado: {resp.status_code}")


class TarefasSecretaria(TaskSet):
    """
    Simula a secretaria cadastrando alunos via app mobile.
    Requisições com multipart/form-data + JPEG sintético.
    """

    @tag("enroll")
    @task(1)
    def enroll_aluno(self):
        jpeg = _jpeg_sintetico()
        matricula = _matricula_aleatoria()
        nome = _nome_aleatorio()
        curso = random.choice([
            "Engenharia de Computação",
            "Ciência da Computação",
            "Sistemas de Informação",
            "Engenharia Elétrica",
        ])
        tipo_vinculo = random.choice(
            ["GRADUACAO", "POS_GRADUACAO", "PROFESSOR", "FUNCIONARIO"]
        )
        turno = random.choice(["MANHA", "TARDE", "NOITE", "INTEGRAL"])

        with self.client.post(
            "/api/v1/access/enroll",
            name="POST /enroll",
            headers={"X-API-Key-Enroll": API_KEY_ENROLL},
            files={"foto": ("foto.jpg", jpeg, "image/jpeg")},
            data={
                "matricula": matricula,
                "nome_completo": nome,
                "curso": curso,
                "tipo_vinculo": tipo_vinculo,
                "turno": turno,
            },
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 422:
                # Esperado: imagem sintética sem rosto real → API valida corretamente
                resp.success()
            elif resp.status_code == 409:
                # Matrícula duplicada — colisão aleatória, não é falha
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Chave de enroll inválida — verifique API_KEY_ENROLL")
            else:
                resp.failure(
                    f"Enroll inesperado {resp.status_code}: {resp.text[:200]}"
                )


class TarefasCatraca(TaskSet):
    """
    Simula o ESP8266 enviando fotos para verificação.
    É o fluxo de maior carga — acontece a cada passagem de aluno.
    """

    def on_start(self):
        # Tenta carregar foto real; cai para sintética se não encontrar
        if os.path.exists(FOTO_VERIFY_PATH):
            self._foto = _jpeg_de_arquivo(FOTO_VERIFY_PATH)
            self._usa_foto_real = True
            print(f"✅ SUCESSO: Carregando foto real para testes: {FOTO_VERIFY_PATH}")
        else:
            self._foto = _jpeg_sintetico(width=160, height=160)
            self._usa_foto_real = False
            print(f"⚠️ AVISO: Arquivo {FOTO_VERIFY_PATH} não encontrado. Usando imagem sintética.")

    @tag("verify")
    @task(1)
    def verify_acesso(self):
        with self.client.post(
            "/api/v1/access/verify",
            name="POST /verify",
            headers={
                "X-API-Key-Device": API_KEY_DEVICE,
                "X-Device-MAC": MAC_ADRESS,
            },
            files={"foto": ("frame.jpg", self._foto, "image/jpeg")},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (403, 422):
                # 403 = rosto não reconhecido / RBAC bloqueou → comportamento correto
                # 422 = imagem sintética sem rosto → esperado no teste de carga
                resp.success()
            elif resp.status_code == 401:
                resp.failure(
                    "Device key ou MAC inválido — "
                    "verifique API_KEY_DEVICE e DEVICE_MAC"
                )
            elif resp.status_code == 500:
                resp.failure(f"Erro interno: {resp.text[:200]}")
            else:
                resp.failure(f"Verify inesperado {resp.status_code}: {resp.text[:200]}")


# ---------------------------------------------------------------------------
# Perfis de usuário — distribuição realista de carga
# ---------------------------------------------------------------------------

class UsuarioMonitoramento(HttpUser):
    """
    Dashboard + load balancer healthcheck.
    Muitas requisições leves — simula N instâncias do painel aberto.
    """
    tasks = [TarefasMonitoramento]
    wait_time = between(0.5, 1.5)   # 40–120 req/min por usuário
    weight = 3                       # 3x mais comum que secretaria


class UsuarioSecretaria(HttpUser):
    """
    Secretaria cadastrando alunos.
    Requisições pesadas (multipart + JPEG) mas menos frequentes.
    """
    tasks = [TarefasSecretaria]
    wait_time = between(2, 5)        # 12–30 req/min por usuário
    weight = 1


class UsuarioCatraca(HttpUser):
    """
    ESP8266 simulado — uma instância por catraca física.
    Fluxo principal: foto → verify → decisão.
    """
    tasks = [TarefasCatraca]
    wait_time = between(1, 3)        # 20–60 req/min por catraca simulada
    weight = 4                       # carga dominante do sistema


# ---------------------------------------------------------------------------
# Hook de relatório — imprime resumo no terminal ao final do teste
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def resumo_final(environment, **kwargs):
    stats = environment.stats
    total   = stats.total
    print("\n" + "=" * 60)
    print("  RESUMO DO TESTE DE ESTRESSE — ACESSO FACIAL")
    print("=" * 60)
    print(f"  Total de requisições : {total.num_requests}")
    print(f"  Falhas               : {total.num_failures}")
    print(f"  Taxa de falha        : {total.fail_ratio * 100:.2f}%")
    print(f"  RPS médio            : {total.current_rps:.1f} req/s")
    print(f"  Req/min              : {total.current_rps * 60:.0f} req/min")
    print(f"  Latência p50         : {total.get_response_time_percentile(0.50):.0f}ms")
    print(f"  Latência p95         : {total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  Latência p99         : {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Latência máxima      : {total.max_response_time:.0f}ms")
    print("=" * 60)

    # Critério de aprovação: ≥ 500 req/min e p95 < 500ms e falha < 1%
    rpm       = total.current_rps * 60
    p95       = total.get_response_time_percentile(0.95)
    falha_pct = total.fail_ratio * 100

    aprovado = rpm >= 500 and p95 < 500 and falha_pct < 1.0

    if aprovado:
        print("  ✅  APROVADO — API suporta ≥ 500 req/min")
    else:
        print("  ❌  REPROVADO — verifique os itens acima")
        if rpm < 500:
            print(f"      → Throughput insuficiente: {rpm:.0f} req/min (mínimo 500)")
        if p95 >= 500:
            print(f"      → p95 alto: {p95:.0f}ms (máximo 500ms)")
        if falha_pct >= 1.0:
            print(f"      → Taxa de falha: {falha_pct:.2f}% (máximo 1%)")
    print("=" * 60 + "\n")