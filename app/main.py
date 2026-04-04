from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from typing import List
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from app.database import get_db, engine
from app import models, schemas
from app.services import vision_service

from fastapi.middleware.cors import CORSMiddleware
import logging

# Configura o logger interno (substitui os prints soltos)
logger = logging.getLogger("uvicorn.error")

# O "CONSTRUTOR" DO BANCO
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema de Acesso Facial - ExpoTech")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, substitua "*" pelos domínios reais do frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# GERENCIADOR DE WEBSOCKETS (Feed em Tempo Real)
# ==========================================
class ConnectionManager:
    def __init__(self):
        # Guarda todos os painéis (dashboards) que estão conectados
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Envia o log da catraca para todos os painéis abertos ao mesmo tempo
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Se um painel caiu sem avisar, marcamos para remover
                disconnected.append(connection)

        for conn in disconnected:
            self.active_connections.remove(conn)


# Instância global do nosso transmissor
manager = ConnectionManager()


@app.websocket("/api/v1/ws/feed")
async def websocket_feed(
    websocket: WebSocket,
    token: str = Query(..., description="Token de autenticação do painel"),  # ✅ FIX: autenticação obrigatória
):
    # ✅ FIX: valida o token ANTES de aceitar a conexão
    # Substitua a lógica abaixo pela sua validação real (ex: JWT, chave estática, etc.)
    VALID_DASHBOARD_TOKENS = {"SEU_TOKEN_SECRETO_AQUI"}  # mova para variável de ambiente
    if token not in VALID_DASHBOARD_TOKENS:
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return

    await manager.connect(websocket)
    try:
        while True:
            # Mantém a conexão aberta escutando o painel
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Um painel de segurança foi desconectado.")


# ==========================================
# CADASTRO DE ALUNO (ENROLL)
# ==========================================
@app.post(
    "/api/v1/access/enroll",
    response_model=schemas.AlunoResponse,
    status_code=201,  # ✅ FIX: criação bem-sucedida retorna 201, não 200
    dependencies=[Depends(require_enroll_key)]
)
async def enroll_student(
    matricula: str = Form(...),
    nome_completo: str = Form(...),
    curso: str = Form(...),
    tipo_vinculo: schemas.TipoVinculoEnum = Form(...),
    turno: schemas.TurnoEnum = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Iniciando cadastro para matrícula: {matricula}")

    # =====================================================================
    # 1. TRADUÇÃO DA IMAGEM
    # =====================================================================
    try:
        foto_bytes = await foto.read()
        vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes)
    except ValueError as e:
        # ✅ FIX: erro causado por dados inválidos do cliente → 422
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # ✅ FIX: erro interno não vaza detalhes para o cliente
        logger.error(f"Falha no vision_service para matrícula {matricula}: {e}")
        raise HTTPException(status_code=500, detail="Falha interna ao processar a imagem.")

    # =====================================================================
    # 2. SEGURANÇA E PERSISTÊNCIA
    # =====================================================================

    # ✅ FIX: idempotência agora retorna 409 explícito em vez de silenciar o conflito
    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == matricula).first()
    if aluno_existente:
        raise HTTPException(
            status_code=409,
            detail=f"Matrícula '{matricula}' já está cadastrada no sistema."
        )

    # UNICIDADE BIOMÉTRICA
    sosia = db.query(models.Aluno).filter(
        models.Aluno.vetor_128d.l2_distance(vetor_128d) < 0.45
    ).first()

    if sosia:
        raise HTTPException(
            status_code=409,
            detail=f"Conflito Biométrico: Rosto muito similar ao do(a) aluno(a) '{sosia.nome_completo}'."
        )

    # SALVA TUDO DE UMA VEZ SÓ (ACID)
    try:
        novo_aluno = models.Aluno(
            matricula=matricula,
            nome_completo=nome_completo,
            curso=curso,
            tipo_vinculo=tipo_vinculo,
            turno=turno,
            vetor_128d=vetor_128d
        )
        db.add(novo_aluno)
        db.commit()
        db.refresh(novo_aluno)
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao persistir aluno {matricula}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar o cadastro.")

    return novo_aluno


# ==========================================
# IDENTIFICAÇÃO FACIAL (CATRACA)
# ==========================================
@app.post("/api/v1/access/identify", dependencies=[Depends(require_device_key)])
def identificar_acesso(request: dict, db: Session = Depends(get_db)):
    """
    Recebe um vetor biométrico e decide se o acesso é liberado.
    Retorna códigos HTTP semânticos que a catraca pode usar diretamente,
    sem precisar inspecionar o corpo da resposta.
    """
    vetor_input = request.get("vetor_128d")

    # ✅ FIX: valida o payload antes de qualquer coisa
    if not vetor_input:
        raise HTTPException(status_code=422, detail="Campo 'vetor_128d' é obrigatório.")

    if len(vetor_input) != 128:
        raise HTTPException(status_code=422, detail=f"Vetor deve ter 128 dimensões, recebeu {len(vetor_input)}.")

    aluno_mais_proximo = db.query(
        models.Aluno,
        models.Aluno.vetor_128d.l2_distance(vetor_input).label("distancia")
    ).order_by("distancia").first()

    # ✅ FIX: banco vazio não é 200 — é um estado que a catraca precisa tratar
    if not aluno_mais_proximo:
        raise HTTPException(
            status_code=503,
            detail="Banco de dados biométrico vazio. Sistema indisponível para identificação."
        )

    aluno, distancia_real = aluno_mais_proximo
    distancia_arredondada = round(distancia_real, 4)

    # ✅ FIX: status codes semânticos — a catraca lê o HTTP status, não o JSON body
    if distancia_real < 0.45:
        # Acesso liberado: 200 OK
        return JSONResponse(
            status_code=200,
            content={
                "acesso": "LIBERADO",
                "nome": aluno.nome_completo,
                "matricula": aluno.matricula,
                "distancia_l2": distancia_arredondada,
            }
        )
    elif distancia_real <= 0.6:
        # Identificação inconclusiva: 202 Accepted (recebeu, mas não confirmou)
        raise HTTPException(
            status_code=202,
            detail={
                "acesso": "INCONCLUSIVO",
                "mensagem": "Similaridade baixa. Recomenda-se validação manual.",
                "distancia_l2": distancia_arredondada,
            }
        )
    else:
        # Acesso negado: 401 Unauthorized
        raise HTTPException(
            status_code=401,
            detail={
                "acesso": "NEGADO",
                "mensagem": "Rosto não reconhecido.",
                "distancia_l2": distancia_arredondada,
            }
        )


# ==========================================
# ROTAS DE TESTE / DIAGNÓSTICO
# ==========================================

@app.get("/teste-enroll", dependencies=[Depends(require_enroll_key)])
async def test_enroll():
    return {"status": "Sucesso", "permissao": "Enroll (Cadastro)"}


@app.get("/teste-admin", dependencies=[Depends(require_admin_key)])
async def test_admin():
    return {"status": "Sucesso", "permissao": "Admin"}


@app.get("/teste-dispositivo")
async def test_device(dispositivo=Depends(require_device_key)):
    return {
        "status": "Sucesso",
        "dispositivo_id": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao,
    }


@app.get("/teste-alunos", response_model=list[schemas.AlunoResponse])
def list_students(db: Session = Depends(get_db)):
    return db.query(models.Aluno).all()

