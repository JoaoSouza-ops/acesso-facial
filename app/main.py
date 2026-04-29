from app.config import get_settings
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, WebSocket, WebSocketException, Query, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from typing import List, Optional
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from app.database import get_db, engine, SessionLocal
from app import models, schemas
from app.services import vision_service, rbac_service
from app.services.face_service import LowQualityImageError

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

import json
import uuid

from datetime import datetime
from sqlalchemy import text




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
 
    settings = get_settings()

    if api_key != settings.api_key_admin:
        # Padrão WS_1008 é a forma correta do protocolo WebSocket dizer "Acesso Negado"
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return api_key

# ==========================================
# Rotas heathcheck
# ==========================================


@app.get("/api/v1/healthz", tags=["System"], summary="Liveness Probe")
def health_check():
    """Verifica se a API está no ar e respondendo a requisições."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/v1/readyz", tags=["System"], summary="Readiness Probe")
def readiness_check(db: Session = Depends(get_db)):
    """Verifica se a API está pronta para receber tráfego (Banco de Dados online)."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness falhou: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable - Database Down")


# ==========================================
# WebSocket para o feed em tempo real dos eventos
# ==========================================

from fastapi import Query, WebSocketException, status

@app.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket, token: str = Query(None)):
    # Validação manual do token via query parameter
    settings = get_settings()
    if token != settings.api_key_admin:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


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
    settings = get_settings()

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
        models.Aluno.vetor_128d.l2_distance(vetor_128d) < settings.THRESHOLD_DUPLICATA
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
# ROTAS ADMINISTRATIVAS (Frontend)
# ==========================================

@app.get("/api/v1/admin/devices", dependencies=[Depends(require_admin_key)], tags=["Admin"])
def get_devices(db: Session = Depends(get_db)):
    """Retorna o status real de todas as catracas conectadas no PostgreSQL"""
    dispositivos = db.query(models.Dispositivo).all()
    return dispositivos

# 1. LISTAR (GET) - O que já temos
@app.get("/api/v1/admin/overrides", 
    response_model=list[schemas.OverrideResponse], 
    dependencies=[Depends(require_admin_key)], 
    tags=["Admin"])

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
@app.post("/api/v1/admin/overrides", 
    status_code=201,
    response_model=schemas.OverrideResponse,
    dependencies=[Depends(require_admin_key)], tags=["Admin"]
    )

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
@app.delete("/api/v1/admin/overrides/{id_override}", dependencies=[Depends(require_admin_key)], tags=["Admin"])

def delete_override(id_override: int, db: Session = Depends(get_db)):
    """Remove uma regra de acesso do banco"""
    target = db.query(models.OverrideAcesso).filter(models.OverrideAcesso.id_override == id_override).first()
    if not target:
        raise HTTPException(status_code=404, detail="Override não encontrado.")
    
    db.delete(target)
    db.commit()
    return {"status": "removido", "id": id_override}


# ── Funções auxiliares das rotas de acesso ────────────────────────────────────

def _montar_payload_ws(dispositivo: models.Dispositivo, distancia: float) -> dict:
    """Monta a base do payload enviado ao WebSocket do feed de segurança."""
    return {
        "id": "evt-" + str(datetime.now().timestamp()),
        "id_dispositivo": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao,
        "ocorrido_em": datetime.now().isoformat(),
        "distancia_l2": distancia,
    }


# Certifique-se de que SessionLocal está importado no topo do arquivo:
# from app.database import get_db, engine, SessionLocal 

def _gravar_evento(id_aluno, id_dispositivo, resultado, codigo_motivo, distancia=None):
    db_bg = SessionLocal() # Inicia uma sessão exclusiva para a task
    try:
        evento = models.EventoAcesso(
            id_aluno=id_aluno,
            id_dispositivo=id_dispositivo,
            resultado=resultado,
            codigo_motivo=codigo_motivo,
            distancia_ia=distancia
        )
        db_bg.add(evento)
        db_bg.commit()
    except Exception as e:
        db_bg.rollback()
        logger.error(f"Falha ao gravar EventoAcesso: {e}")
    finally:
        db_bg.close() # Garante que a conexão retorne ao pool




# ==========================================
# VERIFICAÇÃO FACIAL — CATRACA (ESP32-CAM)
# ==========================================
@app.post(
    "/api/v1/access/verify",
    response_model=schemas.AcessoLiberado,
    status_code=200
)
async def verify_access(
    background_tasks: BackgroundTasks,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    dispositivo: models.Dispositivo = Depends(require_device_key)
):
    """
    Rota principal da catraca. Chamada pelo ESP32-CAM via multipart/form-data.

    Pipeline de 5 etapas:
      1. Extração do vetor facial da imagem recebida
      2. Busca do aluno mais próximo no banco via pgvector
      3. Validação RBAC (4 regras em sequência)
      4. Gravação assíncrona do EventoAcesso (não bloqueia a resposta)
      5. Broadcast do evento para o feed de segurança em tempo real
    """
    request_id = str(uuid.uuid4())

    # ── Etapa 1: Extração do vetor facial ────────────────────────────────────
    foto_bytes = await foto.read()

    if not foto_bytes:
        raise HTTPException(status_code=400, detail="Arquivo de imagem está vazio.")

    try:
        vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes)
    except LowQualityImageError:
        # HTTP 422 sinaliza ao ESP32 para refazer a foto em resolução SVGA
        raise HTTPException(
            status_code=422,
            detail="Qualidade da imagem insuficiente. Tente em resolução SVGA (800x600)."
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Etapa 2: Busca biométrica no banco (pgvector) ─────────────────────────
    resultado_busca = db.query(
        models.Aluno,
        models.Aluno.vetor_128d.l2_distance(vetor_128d).label("distancia")
    ).order_by("distancia").first()

    if not resultado_busca:
        raise HTTPException(
            status_code=503,
            detail="Banco biométrico vazio. Cadastre alunos antes de usar a catraca."
        )

    aluno, distancia = resultado_busca
    distancia = round(float(distancia), 4)

    # Threshold de reconhecimento: distância L2 > 0.6 → rosto desconhecido
    settings = get_settings()
    THRESHOLD = settings.THRESHOLD_ACESSO
    if distancia > THRESHOLD:
        payload_ws = _montar_payload_ws(dispositivo, distancia)
        payload_ws.update({
            "id_aluno": None,
            "nome_aluno": "Desconhecido",
            "resultado": "BLOQUEADO",
            "codigo_motivo": "ROSTO_NAO_RECONHECIDO",
        })
        background_tasks.add_task(_gravar_evento, db, None, dispositivo.id_dispositivo,
                                  "BLOQUEADO", "ROSTO_NAO_RECONHECIDO", distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)

        raise HTTPException(
            status_code=403,
            headers={"X-Request-ID": request_id},
            detail={
                "status": "bloqueado",
                "motivo": "Rosto não reconhecido no sistema.",
                "codigo_motivo": "ROSTO_NAO_RECONHECIDO",
            }
        )

    # ── Etapa 3: Validação RBAC ───────────────────────────────────────────────
    permitido, codigo_motivo = rbac_service.validar_regras_acesso(
        id_aluno=aluno.id_aluno,
        id_dispositivo=dispositivo.id_dispositivo,
        db=db
    )

    payload_ws = _montar_payload_ws(dispositivo, distancia)

    if not permitido:
        payload_ws.update({
            "id_aluno": aluno.id_aluno,
            "nome_aluno": aluno.nome_completo,
            "resultado": "BLOQUEADO",
            "codigo_motivo": codigo_motivo,
        })
        background_tasks.add_task(_gravar_evento, db, aluno.id_aluno,
                                  dispositivo.id_dispositivo, "BLOQUEADO",
                                  codigo_motivo, distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)

        raise HTTPException(
            status_code=403,
            headers={"X-Request-ID": request_id},
            detail={
                "status": "bloqueado",
                "motivo": f"Acesso negado: {codigo_motivo.replace('_', ' ').lower()}.",
                "codigo_motivo": codigo_motivo,
            }
        )

    # ── Etapa 4 e 5: Liberado — grava evento e broadcast ─────────────────────
    payload_ws.update({
        "id_aluno": aluno.id_aluno,
        "nome_aluno": aluno.nome_completo,
        "resultado": "LIBERADO",
        "codigo_motivo": "ACESSO_OK",
    })
    background_tasks.add_task(_gravar_evento, db, aluno.id_aluno,
                              dispositivo.id_dispositivo, "LIBERADO", "", distancia)
    background_tasks.add_task(manager.broadcast, payload_ws)

    return JSONResponse(
        status_code=200,
        headers={"X-Request-ID": request_id},
        content=schemas.AcessoLiberado(
            status="liberado",
            nome=aluno.nome_completo,
            matricula=aluno.matricula,
            tipo_vinculo=aluno.tipo_vinculo,
        ).model_dump()
    )


# ==========================================
# IDENTIFICAÇÃO FACIAL — VIA VETOR JSON
# (Útil para testes via Postman / sem ESP32)
# ==========================================
@app.post("/teste-identify")
async def identificar_acesso(
    background_tasks: BackgroundTasks,
    request: dict,
    db: Session = Depends(get_db),
    dispositivo: models.Dispositivo = Depends(require_device_key)
):
    """
    Alternativa ao /verify para ambientes de teste.
    Recebe o vetor 128D já calculado em vez da imagem bruta.
    Usa a mesma lógica RBAC e grava o mesmo EventoAcesso.
    """
    vetor_input = request.get("vetor_128d")

    if not vetor_input:
        raise HTTPException(status_code=422, detail="Campo 'vetor_128d' é obrigatório.")
    if len(vetor_input) != 128:
        raise HTTPException(
            status_code=422,
            detail=f"Vetor deve ter 128 dimensões, recebeu {len(vetor_input)}."
        )

    # ── Busca biométrica ──────────────────────────────────────────────────────
    resultado_busca = db.query(
        models.Aluno,
        models.Aluno.vetor_128d.l2_distance(vetor_input).label("distancia")
    ).order_by("distancia").first()

    if not resultado_busca:
        raise HTTPException(status_code=503, detail="Banco biométrico vazio.")

    aluno, distancia = resultado_busca
    distancia = round(float(distancia), 4)
    payload_ws = _montar_payload_ws(dispositivo, distancia)

    THRESHOLD = 0.6
    if distancia > THRESHOLD:
        payload_ws.update({
            "id_aluno": None, "nome_aluno": "Desconhecido",
            "resultado": "BLOQUEADO", "codigo_motivo": "ROSTO_NAO_RECONHECIDO",
        })
        background_tasks.add_task(_gravar_evento, db, None, dispositivo.id_dispositivo,
                                  "BLOQUEADO", "ROSTO_NAO_RECONHECIDO", distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)
        raise HTTPException(status_code=403, detail={
            "status": "bloqueado",
            "motivo": "Rosto não reconhecido.",
            "codigo_motivo": "ROSTO_NAO_RECONHECIDO",
        })

    # ── Validação RBAC (mesma função do /verify) ──────────────────────────────
    permitido, codigo_motivo = rbac_service.validar_regras_acesso(
        id_aluno=aluno.id_aluno,
        id_dispositivo=dispositivo.id_dispositivo,
        db=db
    )

    if not permitido:
        payload_ws.update({
            "id_aluno": aluno.id_aluno, "nome_aluno": aluno.nome_completo,
            "resultado": "BLOQUEADO", "codigo_motivo": codigo_motivo,
        })
        background_tasks.add_task(_gravar_evento, db, aluno.id_aluno,
                                  dispositivo.id_dispositivo, "BLOQUEADO",
                                  codigo_motivo, distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)
        raise HTTPException(status_code=403, detail={
            "status": "bloqueado",
            "motivo": f"Acesso negado: {codigo_motivo}",
            "codigo_motivo": codigo_motivo,
        })

    # ── Liberado ──────────────────────────────────────────────────────────────
    payload_ws.update({
        "id_aluno": aluno.id_aluno, "nome_aluno": aluno.nome_completo,
        "resultado": "LIBERADO", "codigo_motivo": "ACESSO_OK",
    })
    background_tasks.add_task(_gravar_evento, db, aluno.id_aluno,
                              dispositivo.id_dispositivo, "LIBERADO", "", distancia)
    background_tasks.add_task(manager.broadcast, payload_ws)

    return JSONResponse(status_code=200, content={
        "status": "liberado",
        "nome": aluno.nome_completo,
        "matricula": aluno.matricula,
        "tipo_vinculo": aluno.tipo_vinculo,
        "distancia_l2": distancia,
    })

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


@app.post("/teste-identify-with-image")
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