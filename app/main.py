from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, WebSocket, WebSocketException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from typing import List, Optional
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from app.database import get_db, engine
from app import models, schemas
from app.services import vision_service

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

import json
import uuid

from datetime import datetime

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

# 1. O Novo "Segurança" do WebSocket
async def verify_ws_key(api_key: str = Query(...)):
    """Verifica a chave de segurança que vem na URL (Query Parameter)"""
    # 🚨 Substitua pela mesma constante ou lógica de banco que você usa no Header
    CHAVE_CORRETA = "chave_secreta_admin_123" 
    
    if api_key != CHAVE_CORRETA:
        # Padrão WS_1008 é a forma correta do protocolo WebSocket dizer "Acesso Negado"
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return api_key

# ==========================================
# WebSocket para o feed em tempo real dos eventos
# ==========================================
@app.websocket("/api/v1/ws/feed")
async def websocket_feed(websocket: WebSocket, api_key: str = Depends(verify_ws_key)):
    # Se chegou aqui, a chave da URL é válida!
    await manager.connect(websocket)
    try:
        while True:
            # Mantém a conexão viva escutando (mesmo que o cliente não mande nada)
            data = await websocket.receive_text()
    except Exception as e:
        manager.disconnect(websocket)


# ==========================================
# CADASTRO DE ALUNO (ENROLL)
# ==========================================

# ==========================================
# CADASTRO DE ALUNO (ENROLL)
# ==========================================
@app.post(
    "/api/v1/access/enroll",
    response_model=schemas.AlunoEnrollado,
    status_code=201,
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

    # ── 1. Extração do vetor facial ──────────────────────────────────────────
    try:
        foto_bytes = await foto.read()
        vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Falha no vision_service para matrícula {matricula}: {e}")
        raise HTTPException(status_code=500, detail="Falha interna ao processar a imagem.")

    # ── 2. Verificação de matrícula duplicada ────────────────────────────────
    aluno_existente = db.query(models.Aluno).filter(
        models.Aluno.matricula == matricula
    ).first()

    if aluno_existente:
        raise HTTPException(
            status_code=409,
            detail={
                "erro": "Matrícula já cadastrada no sistema.",
                "campo": "matricula",
                "valor_conflitante": matricula,
            }
        )

    # ── 3. Verificação de unicidade biométrica ───────────────────────────────
    sosia = db.query(models.Aluno).filter(
        models.Aluno.vetor_128d.l2_distance(vetor_128d) < 0.45
    ).first()

    if sosia:
        raise HTTPException(
            status_code=409,
            detail={
                "erro": f"Conflito biométrico: rosto muito similar ao do aluno '{sosia.nome_completo}'.",
                "campo": "foto",
                "valor_conflitante": sosia.matricula,
            }
        )

    # ── 4. Persistência no banco (ACID) ──────────────────────────────────────
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

    # ── 5. Resposta com header de rastreabilidade ────────────────────────────
    resposta = schemas.AlunoEnrollado(
        id_aluno=novo_aluno.id_aluno,
        matricula=novo_aluno.matricula,
        nome_completo=novo_aluno.nome_completo,
    )

    return JSONResponse(
        status_code=201,
        content=resposta.model_dump(),
        headers={"X-Request-ID": str(uuid.uuid4())},
    )

# ==========================================
# IDENTIFICAÇÃO FACIAL (CATRACA)
# ==========================================
@app.post("/api/v1/access/identify")
async def identificar_acesso(
    request: dict, 
    db: Session = Depends(get_db),
    # 🟢 Pegamos os dados do dispositivo logado para mandar pro Feed!
    dispositivo = Depends(require_device_key) 
):
    """
    Recebe um vetor biométrico e decide se o acesso é liberado.
    Dispara o resultado para o Feed de Segurança em tempo real.
    """
    vetor_input = request.get("vetor_128d")

    if not vetor_input:
        raise HTTPException(status_code=422, detail="Campo 'vetor_128d' é obrigatório.")

    if len(vetor_input) != 128:
        raise HTTPException(status_code=422, detail=f"Vetor deve ter 128 dimensões, recebeu {len(vetor_input)}.")

    aluno_mais_proximo = db.query(
        models.Aluno,
        models.Aluno.vetor_128d.l2_distance(vetor_input).label("distancia")
    ).order_by("distancia").first()

    if not aluno_mais_proximo:
        raise HTTPException(
            status_code=503,
            detail="Banco de dados biométrico vazio. Sistema indisponível para identificação."
        )

    aluno, distancia_real = aluno_mais_proximo
    distancia_arredondada = round(distancia_real, 4)

    # 🟢 Base do Payload para o React Native (com dados reais da catraca)
    payload_ws = {
        "id": "evt-" + str(datetime.now().timestamp()),
        "id_dispositivo": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao,
        "ocorrido_em": datetime.now().isoformat()
    }

    if distancia_real < 0.45:
        # ==========================================
        # ACESSO LIBERADO
        # ==========================================
        payload_ws.update({
            "id_aluno": aluno.id_aluno,
            "nome_aluno": aluno.nome_completo,
            "resultado": "LIBERADO",
            "codigo_motivo": "ACESSO_OK"
        })
        await manager.broadcast(payload_ws) # 🟢 Dispara pro App

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
        # ==========================================
        # INCONCLUSIVO / DESCONHECIDO
        # ==========================================
        payload_ws.update({
            "id_aluno": None,
            "nome_aluno": "Desconhecido",
            "resultado": "DESCONHECIDO",
            "codigo_motivo": "SIMILARIDADE_BAIXA"
        })
        await manager.broadcast(payload_ws) # 🟢 Dispara pro App

        raise HTTPException(
            status_code=202,
            detail={
                "acesso": "INCONCLUSIVO",
                "mensagem": "Similaridade baixa. Recomenda-se validação manual.",
                "distancia_l2": distancia_arredondada,
            }
        )
        
    else:
        # ==========================================
        # ACESSO NEGADO / BLOQUEADO
        # ==========================================
        payload_ws.update({
            "id_aluno": None,
            "nome_aluno": "Desconhecido",
            "resultado": "BLOQUEADO",
            "codigo_motivo": "ROSTO_NAO_RECONHECIDO"
        })
        await manager.broadcast(payload_ws) # 🟢 Dispara pro App

        raise HTTPException(
            status_code=401,
            detail={
                "acesso": "NEGADO",
                "mensagem": "Rosto não reconhecido.",
                "distancia_l2": distancia_arredondada,
            }
        )

# ==========================================
# ROTAS ADMINISTRATIVAS (Frontend)
# ==========================================

@app.get("/api/v1/admin/devices")
def get_devices(db: Session = Depends(get_db)):
    """Retorna o status real de todas as catracas conectadas no PostgreSQL"""
    dispositivos = db.query(models.Dispositivo).all()
    return dispositivos

# 1. LISTAR (GET) - O que já temos
@app.get("/api/v1/admin/overrides", response_model=list[schemas.OverrideResponse])
def get_overrides(db: Session = Depends(get_db)):
    # FIX #2: usa joinedload para que item.aluno.nome_completo chegue preenchido no frontend
    return db.query(models.OverrideAcesso)\
        .options(joinedload(models.OverrideAcesso.aluno))\
        .all()

# Schema para criação de override (evita o 500 por dict sem validação)
class OverrideCreate(BaseModel):
    id_aluno: int
    bloco: str
    tipo_override: str
    motivo: Optional[str] = None
    nome_aluno: Optional[str] = None  # ignorado — nome vem do relacionamento com alunos


# 2. CRIAR (POST) - Persistência Real
@app.post("/api/v1/admin/overrides", status_code=201, response_model=schemas.OverrideResponse)
def create_override(obj_in: OverrideCreate, db: Session = Depends(get_db)):
    # 1. Validação do Aluno — obj_in.id_aluno é garantidamente int pelo Pydantic
    aluno_existe = db.query(models.Aluno).filter(models.Aluno.id_aluno == obj_in.id_aluno).first()

    if not aluno_existe:
        raise HTTPException(
            status_code=404,
            detail=f"Aluno com id_aluno={obj_in.id_aluno} não encontrado. Verifique se o aluno está cadastrado."
        )

    try:
        # 2. Criação Simples
        novo_override = models.OverrideAcesso(
            id_aluno=obj_in.id_aluno,
            bloco=obj_in.bloco,
            tipo_override=obj_in.tipo_override,
            motivo=obj_in.motivo
        )
        db.add(novo_override)
        db.commit()

        # 3. Busca final com aluno embutido para o response_model serializar corretamente
        resultado = db.query(models.OverrideAcesso)\
            .options(joinedload(models.OverrideAcesso.aluno))\
            .filter(models.OverrideAcesso.id_override == novo_override.id_override)\
            .first()

        return resultado

    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar override: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao processar override.")


# 3. DELETAR (DELETE) - Remoção por ID
@app.delete("/api/v1/admin/overrides/{id_override}")
def delete_override(id_override: int, db: Session = Depends(get_db)):
    """Remove uma regra de acesso do banco"""
    target = db.query(models.OverrideAcesso).filter(models.OverrideAcesso.id_override == id_override).first()
    if not target:
        raise HTTPException(status_code=404, detail="Override não encontrado.")
    
    db.delete(target)
    db.commit()
    return {"status": "removido", "id": id_override}


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


from fastapi import HTTPException # 🟢 Não esqueça de importar o HTTPException no topo!

@app.post("/api/v1/access/test-identify-with-image")
async def test_identify_image(foto: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Extração
    foto_bytes = await foto.read()
    vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes)
    
    # 2. Busca pgvector
    sosia = db.query(models.Aluno).filter(
        models.Aluno.vetor_128d.l2_distance(vetor_128d) < 0.45
    ).first()
    
    # ==========================================
    # CASO 1: ROSTO DESCONHECIDO
    # ==========================================
    if not sosia:
        payload_erro = {
            "id": "desc-" + str(datetime.now().timestamp()),
            "nome_aluno": "Desconhecido",
            "resultado": "DESCONHECIDO",
            "localizacao": "Portaria Principal",
            "codigo_motivo": "FACE_NAO_RECONHECIDA",
            "ocorrido_em": datetime.now().isoformat()
        }
        # Dispara o card AMARELO/VERMELHO no aplicativo do Hericles
        await manager.broadcast(payload_erro)
        
        # 🔴 Retorna ERRO 403 para a catraca não abrir!
        raise HTTPException(status_code=403, detail=payload_erro)

    # ==========================================
    # CASO 2: ALUNO ENCONTRADO (LIBERADO)
    # ==========================================
    payload_sucesso = {
        "id": str(sosia.id_aluno),
        "nome_aluno": sosia.nome_completo,
        "resultado": "LIBERADO",
        "localizacao": "Portaria Principal",
        "codigo_motivo": "ACESSO_OK",
        "ocorrido_em": datetime.now().isoformat()
    }
    
    # Dispara o card VERDE no aplicativo
    await manager.broadcast(payload_sucesso)
    
    # 🟢 Retorna 200 OK para a catraca abrir!
    return payload_sucesso