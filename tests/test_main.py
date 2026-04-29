import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

# Importa as dependências do seu projeto
from app.main import app
from app.database import get_db, Base
from app.config import get_settings
from app import models

import os

# ==========================================
# 1. SETUP: BANCO DE DADOS DE TESTE EM MEMÓRIA
# ==========================================
# Usamos SQLite em memória para que os testes rodem super rápido e não sujem o banco de produção.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Sobrescreve a dependência original pela de teste
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Executado antes de cada teste para criar as tabelas limpas
@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ==========================================
# 2. TESTES DE EXCELÊNCIA (Health Checks)
# ==========================================
def test_healthz_liveness_probe():
    """Valida se o health check básico responde corretamente."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "timestamp" in response.json()

def test_readyz_readiness_probe_success():
    """Valida se o readiness check consegue se comunicar com o banco de dados."""
    response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


# ==========================================
# 3. TESTES DO BUG DE SEGURANÇA (Rotas Admin Expostas)
# ==========================================
def test_admin_routes_without_auth_must_fail():
    admin_endpoints = ["/api/v1/admin/devices", "/api/v1/admin/overrides"]
    for endpoint in admin_endpoints:
        # Envie uma chave falsa/inválida para passar pela validação 422 
        # e cair na lógica de rejeição 401/403 da sua dependência
        headers = {"X-API-Key-Admin": "CHAVE_FALSA_INVALIDA"} 
        response = client.get(endpoint, headers=headers)
        assert response.status_code in [401, 403], f"A rota {endpoint} está exposta!"


def test_admin_routes_with_valid_auth():
    """Valida se a injeção da chave de admin permite o acesso."""
    settings = get_settings()
    headers = {"X-API-Key-Admin": "chave_secreta_admin_123"} 
    response = client.get("/api/v1/admin/devices", headers=headers)
    
    # ADICIONE ESTAS DUAS LINHAS:
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    

# ==========================================
# 4. TESTE DO BUG DE DEPENDÊNCIA DUPLICADA
# ==========================================

def test_verify_access_dependency_injection():
    files = {"foto": ("dummy.jpg", b"fake_bytes", "image/jpeg")}
    
    # CORREÇÃO: Adicionado o X-Device-MAC que é exigido pelo auth.py
    headers = {
        "X-API-Key-Device": "CHAVE_FALSA_INVALIDA",
        "X-Device-MAC": "00:00:00:00:00:00"
    }

    response_unauthorized = client.post("/api/v1/access/verify", files=files, headers=headers)
    assert response_unauthorized.status_code in [401, 403]


# ==========================================
# 5. TESTE CRÍTICO: SESSÃO NO BACKGROUND TASK
# ==========================================

import os

# ==========================================
# TESTE CRÍTICO: SESSÃO NO BACKGROUND TASK (E2E com Foto Real)
# ==========================================

def test_background_task_database_session_persistence(monkeypatch):
    import app.main
    # Força a função a usar o banco em memória
    monkeypatch.setattr(app.main, "SessionLocal", TestingSessionLocal)
    
    db = TestingSessionLocal()
    
    # 1. Cria o dispositivo fake
    disp_teste = models.Dispositivo(
        api_key="hub-dev-device-chave-secreta-001",
        localizacao="Lab 1",
        bloco="A",
        mac_address="AA:BB:CC:DD:EE:FF"
    ) 
    db.add(disp_teste)
    db.commit()
    db.refresh(disp_teste)
    
    # 2. Chama a BackgroundTask DIRETAMENTE, pulando a matemática do pgvector
    app.main._gravar_evento(
        id_aluno=None,
        id_dispositivo=disp_teste.id_dispositivo,
        resultado="TESTE_UNITARIO",
        codigo_motivo="VALIDACAO_SESSAO",
        distancia=0.0
    )
    
    # 3. Verifica se gravou
    evento = db.query(models.EventoAcesso).filter_by(codigo_motivo="VALIDACAO_SESSAO").first()
    
    # O PULO DO GATO: Se for None, a função tentou gravar e deu erro (ex: nome de coluna errada)
    # e o bloco "try/except" do main.py escondeu o erro.
    if evento is None:
        pytest.fail(
            "A função rodou, mas o evento não foi salvo! "
            "Verifique no seu main.py se os campos dentro de _gravar_evento() "
            "estão com os nomes EXATOS do seu models.EventoAcesso. "
            "(Dica: verifique se é 'distancia' ou 'distancia_ia')"
        )
        
    assert evento is not None, "A BackgroundTask falhou ao gravar o evento!"
    db.close()