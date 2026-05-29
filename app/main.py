from app.config import get_settings
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, WebSocket, WebSocketException, Query, status, BackgroundTasks, Request, Header
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Any

from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from app.database import get_db, engine, SessionLocal
from app import models, schemas
from app.services import vision_service, rbac_service
from app.services.face_service import LowQualityImageError

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging
import json
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger("uvicorn.error")
models.Base.metadata.create_all(bind=engine)

# ==========================================
# 1. METADADOS E INFORMAÇÕES DE ROTEAMENTO (servers e info.contact)
# ==========================================
app = FastAPI(
    title="Sistema de Acesso Facial - ExpoTech",
    version="1.2.1",
    contact={
        "name": "Suporte Polinômicos",
        "email": "contato@expotech.edu.br"
    },
    license_info={
        "name": "MIT"
    },
    servers=[
        {"url": "https://api.hub.edu.br", "description": "Produção AWS"},
        {"url": "http://localhost:8000", "description": "Desenvolvimento Local"}
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. PADRONIZAÇÃO DOS ERROS HTTP (401, 403, 409, 503) E PROBLEMAS (RFC 7807)
# ==========================================
class ProblemDetails(BaseModel):
    type: str = Field("about:blank", description="URI que identifica o tipo do problema")
    title: str = Field(..., description="Resumo curto e legível para humanos do problema")
    status: int = Field(..., description="O código de status HTTP")
    detail: Optional[str] = Field(None, description="Explicação legível por humanos sobre esta ocorrência do problema")
    instance: Optional[str] = Field(None, description="Referência URI que identifica a ocorrência específica do problema")

COMMON_RESPONSES = {
    400: {"description": "Bad Request", "model": ProblemDetails},
    401: {"description": "Unauthorized - Chave de API ausente ou inválida", "model": ProblemDetails},
    403: {"description": "Forbidden - Permissão insuficiente para a ação (ou acesso negado)", "model": ProblemDetails},
    409: {"description": "Conflict - Conflito biométrico ou quebra de regras", "model": ProblemDetails},
    422: {"description": "Unprocessable Entity - Falha na validação semântica da imagem ou body"},
    429: {
        "description": "Too Many Requests - Limite de requisições excedido", 
        "model": ProblemDetails,
        "headers": {
            "Retry-After": {"description": "Segundos a aguardar antes de tentar novamente", "schema": {"type": "integer"}},
            "X-RateLimit-Limit": {"description": "Limite máximo de requisições por período", "schema": {"type": "integer"}},
            "X-RateLimit-Remaining": {"description": "Requisições restantes no período atual", "schema": {"type": "integer"}}
        }
    },
    500: {"description": "Internal Server Error - Erro inesperado da infraestrutura", "model": ProblemDetails},
    503: {"description": "Service Unavailable - Banco de dados offline ou limpo", "model": ProblemDetails}
}

_dlib_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dlib")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

manager = ConnectionManager()


class HealthzResponse(BaseModel):
    status: str = Field("ok", description="Status do processo")
    timestamp: str = Field(..., description="Timestamp ISO do momento")

class ReadyzResponse(BaseModel):
    status: str = Field(..., description="Status de prontidão")
    database: str = Field(..., description="Status da dependência de banco de dados")

@app.get("/api/v1/healthz", tags=["System"], summary="Liveness Probe", response_model=HealthzResponse)
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/v1/readyz", tags=["System"], summary="Readiness Probe", response_model=ReadyzResponse, responses={**COMMON_RESPONSES})
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "online"}
    except Exception as e:
        logger.error(f"Readiness falhou: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable - Database Down")

from starlette.websockets import WebSocketDisconnect


@app.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket, token: str = Query(None)):
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


@app.post(
    "/api/v1/access/enroll",
    response_model=schemas.AlunoEnrollado,
    status_code=201,
    dependencies=[Depends(require_enroll_key)],
    responses={**COMMON_RESPONSES}
)
async def enroll_student(
    matricula: str = Form(...),
    nome_completo: str = Form(...),
    curso: str = Form(...),
    tipo_vinculo: schemas.TipoVinculoEnum = Form(...),
    turno: schemas.TurnoEnum = Form(...),
    foto: UploadFile = File(...),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description="Chave UUID para evitar duplicidade em retentativas na inclusão de cadastro"),
    db: Session = Depends(get_db)
):
    logger.info(f"Iniciando cadastro para matrícula: {matricula}")
    settings = get_settings()
    try:
        foto_bytes = await foto.read()
        loop = asyncio.get_event_loop()
        vetor_128d = await loop.run_in_executor(_dlib_executor, vision_service.extrair_vetor_da_imagem, foto_bytes)
    except LowQualityImageError:
        raise HTTPException(status_code=422, detail="Qualidade da imagem insuficiente.")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Falha no vision_service para matrícula {matricula}: {e}")
        raise HTTPException(status_code=500, detail="Falha interna ao processar a imagem.")

    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == matricula).first()
    if aluno_existente:
        raise HTTPException(status_code=409, detail={"erro": "Matrícula já cadastrada no sistema.", "campo": "matricula", "valor_conflitante": matricula})

    sosia = db.query(models.Aluno).filter(models.Aluno.vetor_128d.l2_distance(vetor_128d) < settings.THRESHOLD_DUPLICATA).first()
    if sosia:
        raise HTTPException(status_code=409, detail={"erro": f"Conflito biométrico com o aluno '{sosia.nome_completo}'.", "campo": "foto", "valor_conflitante": sosia.matricula})

    try:
        novo_aluno = models.Aluno(matricula=matricula, nome_completo=nome_completo, curso=curso, tipo_vinculo=tipo_vinculo, turno=turno, vetor_128d=vetor_128d)
        db.add(novo_aluno)
        db.commit()
        db.refresh(novo_aluno)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao salvar o cadastro.")

    resposta = schemas.AlunoEnrollado(id_aluno=novo_aluno.id_aluno, matricula=novo_aluno.matricula, nome_completo=novo_aluno.nome_completo)
    return JSONResponse(status_code=201, content=resposta.model_dump(), headers={"X-Request-ID": str(uuid.uuid4())})

class DeviceResponse(BaseModel):
    id_dispositivo: int = Field(..., description="ID interno do dispositivo")
    mac_address: str = Field(..., description="Endereço MAC da catraca")
    localizacao: str = Field(..., description="Localização descritiva da catraca")
    bloco: Optional[str] = Field(None, description="Bloco físico associado")
    ultima_atividade: Optional[datetime] = Field(None, description="Timestamp da última atividade")
    status_bateria: Optional[str] = Field(None, description="Status da bateria ou alimentação")

    class Config:
        from_attributes = True

class PaginatedDeviceResponse(BaseModel):
    data: List[DeviceResponse]
    total: int
    page: int
    size: int
    pages: int

class PaginatedOverrideResponse(BaseModel):
    data: List[schemas.OverrideResponse]
    total: int
    page: int
    size: int
    pages: int

@app.get("/api/v1/admin/devices", response_model=PaginatedDeviceResponse, dependencies=[Depends(require_admin_key)], tags=["Admin"], responses={**COMMON_RESPONSES})
def get_devices(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    total = db.query(models.Dispositivo).count()
    dispositivos = db.query(models.Dispositivo).offset((page - 1) * size).limit(size).all()
    return {
        "data": dispositivos,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size
    }

@app.get("/api/v1/admin/overrides", response_model=PaginatedOverrideResponse, dependencies=[Depends(require_admin_key)], tags=["Admin"], responses={**COMMON_RESPONSES})
def get_overrides(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(models.OverrideAcesso).options(joinedload(models.OverrideAcesso.aluno))
    total = query.count()
    overrides = query.offset((page - 1) * size).limit(size).all()
    return {
        "data": overrides,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size
    }

# ==========================================
# 3. CONTRATO SCHEMAS MELHORADOS - OverrideCreate
# ==========================================
class OverrideCreate(BaseModel):
    """Esquema para criação de nova regra de exceção (override) de acesso no motor RBAC"""
    id_aluno: int = Field(..., description="ID interno do aluno associado a exceção")
    bloco: str = Field(..., description="Identificador do bloco físico visado")
    tipo_override: str = Field(..., description="Ação da política: PERMITIR ou BLOQUEAR")
    motivo: Optional[str] = Field(None, description="Justificativa administrativa da liberação de evento")
    nome_aluno: Optional[str] = Field(None, description="Opcional - preenchido no log para histórico")


@app.post("/api/v1/admin/overrides", status_code=201, response_model=schemas.OverrideResponse, dependencies=[Depends(require_admin_key)], tags=["Admin"], responses={**COMMON_RESPONSES})
def create_override(
    obj_in: schemas.OverrideCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description="Chave UUID para evitar duplicidade em retentativas"),
    db: Session = Depends(get_db)
):
    # 1. Busca o aluno pela MATRÍCULA
    aluno_existe = db.query(models.Aluno).filter(models.Aluno.matricula == obj_in.matricula).first()
    
    if not aluno_existe:
        raise HTTPException(status_code=404, detail=f"Matrícula {obj_in.matricula} não encontrada na base de dados.")
        
    try:
        # 2. Usa o ID do aluno encontrado para gravar na tabela OverrideAcesso
        novo_override = models.OverrideAcesso(
            id_aluno=aluno_existe.id_aluno, 
            bloco=obj_in.bloco, 
            tipo_override=obj_in.tipo_override, 
            motivo=obj_in.motivo
        )
        db.add(novo_override)
        db.commit()
        
        resultado = db.query(models.OverrideAcesso).options(joinedload(models.OverrideAcesso.aluno)).filter(models.OverrideAcesso.id_override == novo_override.id_override).first()
        return resultado
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao processar override.")

@app.delete("/api/v1/admin/overrides/{id_override}", dependencies=[Depends(require_admin_key)], tags=["Admin"], responses={**COMMON_RESPONSES})
def delete_override(id_override: int, db: Session = Depends(get_db)):
    target = db.query(models.OverrideAcesso).filter(models.OverrideAcesso.id_override == id_override).first()
    if not target:
        raise HTTPException(status_code=404, detail="Override não encontrado.")
    db.delete(target)
    db.commit()
    return {"status": "removido", "id": id_override}

def _montar_payload_ws(dispositivo: models.Dispositivo, distancia: float) -> dict:
    return {
        "id": "evt-" + str(datetime.now().timestamp()),
        "id_dispositivo": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao,
        "ocorrido_em": datetime.now().isoformat(),
        "distancia_l2": distancia,
    }



def _gravar_evento(id_aluno, id_dispositivo, resultado, codigo_motivo, distancia=None):
    db_bg = SessionLocal()
    try:
        evento = models.EventoAcesso(id_aluno=id_aluno, id_dispositivo=id_dispositivo, resultado=resultado, codigo_motivo=codigo_motivo, distancia_ia=distancia)
        db_bg.add(evento)
        db_bg.commit()
    except Exception as e:
        db_bg.rollback()
        logger.error(f"Falha ao gravar EventoAcesso: {e}")
    finally:
        db_bg.close()


# ==========================================
# 4. HEADER X-REQUEST-ID DOCUMENTADO NO RESPONSE DA VERIFY
# ==========================================
@app.post(
    "/api/v1/access/verify",
    response_model=schemas.AcessoLiberado,
    status_code=200,
    responses={
        **COMMON_RESPONSES,
        200: {
            "description": "Acesso Liberado com sucesso",
            "headers": {
                "X-Request-ID": {
                    "description": "Token único para rastreabilidade de correlação entre logs e endpoints",
                    "schema": {"type": "string"}
                }
            }
        }
    }
)
async def verify_access(
    background_tasks: BackgroundTasks,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    dispositivo: models.Dispositivo = Depends(require_device_key)
):
    request_id = str(uuid.uuid4())
    foto_bytes = await foto.read()

    if not foto_bytes:
        raise HTTPException(status_code=400, detail="Arquivo de imagem está vazio.")

    try:
        loop = asyncio.get_event_loop()
        vetor_128d = await loop.run_in_executor(_dlib_executor, vision_service.extrair_vetor_da_imagem, foto_bytes)
    except LowQualityImageError:
        raise HTTPException(status_code=422, detail="Qualidade da imagem insuficiente. Tente em resolução SVGA (800x600).")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resultado_busca = db.query(models.Aluno, models.Aluno.vetor_128d.l2_distance(vetor_128d).label("distancia")).order_by("distancia").first()

    if not resultado_busca:
        raise HTTPException(status_code=503, detail="Banco biométrico vazio. Cadastre alunos antes de usar a catraca.")

    aluno, distancia = resultado_busca
    distancia = round(float(distancia), 4)

    settings = get_settings()
    THRESHOLD = settings.THRESHOLD_ACESSO
    if distancia > THRESHOLD:
        payload_ws = _montar_payload_ws(dispositivo, distancia)
        payload_ws.update({"id_aluno": None, "nome_aluno": "Desconhecido", "resultado": "BLOQUEADO", "codigo_motivo": "ROSTO_NAO_RECONHECIDO"})
        background_tasks.add_task(_gravar_evento, None, dispositivo.id_dispositivo, "BLOQUEADO", "ROSTO_NAO_RECONHECIDO", distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)
        raise HTTPException(status_code=403, headers={"X-Request-ID": request_id}, detail={"status": "bloqueado", "motivo": "Rosto não reconhecido no sistema.", "codigo_motivo": "ROSTO_NAO_RECONHECIDO"})

    permitido, codigo_motivo = rbac_service.validar_regras_acesso(id_aluno=aluno.id_aluno, id_dispositivo=dispositivo.id_dispositivo, db=db)
    payload_ws = _montar_payload_ws(dispositivo, distancia)

    if not permitido:
        payload_ws.update({"id_aluno": aluno.id_aluno, "nome_aluno": aluno.nome_completo, "resultado": "BLOQUEADO", "codigo_motivo": codigo_motivo})
        background_tasks.add_task(_gravar_evento, aluno.id_aluno, dispositivo.id_dispositivo, "BLOQUEADO", codigo_motivo, distancia)
        background_tasks.add_task(manager.broadcast, payload_ws)
        raise HTTPException(status_code=403, headers={"X-Request-ID": request_id}, detail={"status": "bloqueado", "motivo": f"Acesso negado: {codigo_motivo.replace('_', ' ').lower()}.", "codigo_motivo": codigo_motivo})

    payload_ws.update({"id_aluno": aluno.id_aluno, "nome_aluno": aluno.nome_completo, "resultado": "LIBERADO", "codigo_motivo": "ACESSO_OK"})
    background_tasks.add_task(_gravar_evento, aluno.id_aluno, dispositivo.id_dispositivo, "LIBERADO", "", distancia)
    background_tasks.add_task(manager.broadcast, payload_ws)

    return JSONResponse(status_code=200, headers={"X-Request-ID": request_id}, content=schemas.AcessoLiberado(status="liberado", nome=aluno.nome_completo, matricula=aluno.matricula, tipo_vinculo=aluno.tipo_vinculo).model_dump())

# ==========================================
# 5. ROTAS DE TESTE COM FLAG DE DEPRECATION / EXCLUSÃO
# ==========================================

@app.post("/teste-identify", tags=["Testes"], deprecated=True, responses={**COMMON_RESPONSES})
async def identificar_acesso(background_tasks: BackgroundTasks, request: dict, db: Session = Depends(get_db), dispositivo: models.Dispositivo = Depends(require_device_key)):
    vetor_input = request.get("vetor_128d")
    # Logica simulatória para ambiente de teste
    return JSONResponse(status_code=200, content={"status": "mock via post"})

@app.get("/teste-enroll", dependencies=[Depends(require_enroll_key)], tags=["Testes"], deprecated=True)
async def test_enroll():
    return {"status": "Sucesso", "permissao": "Enroll (Cadastro)"}

@app.get("/teste-admin", dependencies=[Depends(require_admin_key)], tags=["Testes"], deprecated=True)
async def test_admin():
    return {"status": "Sucesso", "permissao": "Admin"}

@app.get("/teste-dispositivo", tags=["Testes"], deprecated=True)
async def test_device(dispositivo=Depends(require_device_key)):
    return {"status": "Sucesso", "dispositivo_id": dispositivo.id_dispositivo}

@app.get("/teste-alunos", response_model=list[schemas.AlunoResponse], tags=["Testes"], deprecated=True)
def list_students(db: Session = Depends(get_db)):
    return db.query(models.Aluno).all()

@app.post("/teste-identify-with-image", tags=["Testes"], deprecated=True)
async def test_identify_image(foto: UploadFile = File(...), db: Session = Depends(get_db)):
    return {"status": "Sucesso"}

@app.post("/api/v1/access/teste", tags=["Testes"], deprecated=True)
async def teste_upload(foto: UploadFile = File(...)):
    conteudo = await foto.read()
    return {"status": "sucesso", "bytes_recebidos": len(conteudo)}

# ==========================================
# 6. CONFIGURAÇÃO CANÔNICA DE AUTENTICAÇÃO (securitySchemes) NO OPENAPI.JSON
# ==========================================
def custom_openapi():
    # Retorna o schema caso já formatado
    if app.openapi_schema:
        return app.openapi_schema

    # 1. Utiliza a Factory Helper para construir o core OAS do app.
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        contact=app.contact,
        license_info=app.license_info,
        servers=app.servers
    )

    # 2. Definição explícita do bloco securitySchemes na Documentação
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyDevice": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key-Device",
            "description": "Token para o hardware IoT na borda de catracas (ESP32)"
        },
        "ApiKeyEnroll": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key-Enroll",
            "description": "Token gerencial para autorizar novos alunos via matricula"
        },
        "ApiKeyAdmin": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key-Admin",
            "description": "Token de acesso total exigido nos recursos do dashboard administrativo"
        }
    }

    # 3. Limpar a poluição dos Security-Parameters vindos de Depends puros para tags Security padrao
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            
            sec_req = []
            
            # Inferência de tipo por endpoint path:
            if "/admin" in path or "teste-admin" in path or "/ws" in path:
                sec_req.append({"ApiKeyAdmin": []})
            elif "/enroll" in path or "teste-enroll" in path:
                sec_req.append({"ApiKeyEnroll": []})
            elif "/verify" in path or "teste-dispositivo" in path or "teste-identify" in path:
                sec_req.append({"ApiKeyDevice": []})

            # Varrendo e limpando parâmetros em header das rotas que repetem as Keys
            params = operation.get("parameters", [])
            clean_params = []
            for p in params:
                if p.get("in") == "header" and "X-API-Key" in p.get("name", ""):
                    continue  # Foi mapeado acima pelo securitySchemes
                clean_params.append(p)
            
            if clean_params:
                operation["parameters"] = clean_params
            elif "parameters" in operation:
                del operation["parameters"] # Remove caso nao tenhamos outros pametros
            
            # Injeta security mapping de OAS 3.1.0 global
            if sec_req:
                operation["security"] = sec_req

            # 4. Restrição de MIME types para uploads (application/octet-stream -> image/jpeg) no operation
            if "requestBody" in operation:
                content = operation["requestBody"].get("content", {})
                if "multipart/form-data" in content:
                    props = content["multipart/form-data"].get("schema", {}).get("properties", {})
                    if "foto" in props:
                        props["foto"]["contentMediaType"] = "image/jpeg, image/jpg"
                        props["foto"]["description"] = "Imagem facial (JPEG) recomendada SVGA. Tamanho máximo recomendado 2MB para desempenho na borda."

    # 5. Restruturação das referências dos Bodies (FastAPI extrai propriedades complexas para os components)
    if "components" in openapi_schema and "schemas" in openapi_schema["components"]:
        for schema_name, schema_obj in openapi_schema["components"]["schemas"].items():
            if schema_name.startswith("Body_") and "properties" in schema_obj:
                props = schema_obj["properties"]
                if "foto" in props:
                    props["foto"]["contentMediaType"] = "image/jpeg, image/jpg"
                    props["foto"]["description"] = "Imagem facial (JPEG) obrigatória. Resolução preferencial SVGA."

    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Override da documentação do framework pelo gerador customizado
app.openapi = custom_openapi
