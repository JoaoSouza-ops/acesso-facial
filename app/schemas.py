from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime

# ==========================================
# 1. ENUMS (A blindagem contra dados errados)
# ==========================================
class TipoVinculoEnum(str, Enum):
    GRADUACAO = 'GRADUACAO'
    POS_GRADUACAO = 'POS_GRADUACAO'
    PROFESSOR = 'PROFESSOR'
    FUNCIONARIO = 'FUNCIONARIO'

class TurnoEnum(str, Enum):
    MANHA = 'MANHA'
    TARDE = 'TARDE'
    NOITE = 'NOITE'
    INTEGRAL = 'INTEGRAL'

class StatusAcessoEnum(str, Enum):
    ATIVO = 'ATIVO'
    BLOQUEADO = 'BLOQUEADO'

class BlocoEnum(str, Enum):
    SEDE = 'SEDE'
    BLOCO_AULAS = 'BLOCO_AULAS'

class ResultadoAcessoEnum(str, Enum):
    LIBERADO = 'LIBERADO'
    BLOQUEADO = 'BLOQUEADO'
    DESCONHECIDO = 'DESCONHECIDO'


# ==========================================
# 2. SCHEMAS DE ALUNOS
# ==========================================
class AlunoBase(BaseModel):
    matricula: str = Field(..., max_length=20, description="Matrícula única do aluno")
    nome_completo: str = Field(..., max_length=255)
    curso: str = Field(..., max_length=100)
    tipo_vinculo: TipoVinculoEnum
    turno: TurnoEnum
    status_acesso: StatusAcessoEnum = StatusAcessoEnum.ATIVO

class AlunoCreate(AlunoBase):
    pass
    # Nota: Não incluímos a foto/vetor aqui porque a foto viaja via UploadFile 
    # no endpoint, e o vetor é gerado pela nossa IA no backend.

class AlunoResponse(AlunoBase):
    id_aluno: int
    criado_em: datetime
    
    # from_attributes=True permite que o Pydantic leia objetos do SQLAlchemy
    model_config = ConfigDict(from_attributes=True) 


# ==========================================
# 3. SCHEMAS DE OVERRIDES
# ==========================================
class AlunoEmOverride(BaseModel):
    """Subconjunto do aluno embutido na resposta de override (evita expor vetor biométrico)."""
    id_aluno: int
    nome_completo: str
    matricula: str

    model_config = ConfigDict(from_attributes=True)

class OverrideResponse(BaseModel):
    id_override: int
    id_aluno: int
    bloco: str
    tipo_override: str
    motivo: Optional[str] = None
    criado_em: datetime
    aluno: Optional[AlunoEmOverride] = None  # preenchido pelo joinedload no backend

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. SCHEMAS DE DISPOSITIVOS E EVENTOS (Dashboard)
# ==========================================
class DispositivoResponse(BaseModel):
    id_dispositivo: int
    localizacao: str
    bloco: BlocoEnum
    is_ativo: bool

    model_config = ConfigDict(from_attributes=True)

class EventoAcessoResponse(BaseModel):
    id_evento: int
    resultado: ResultadoAcessoEnum
    codigo_motivo: Optional[str] = None
    criado_em: datetime
    # Trazemos os dados do aluno e do dispositivo aninhados para o Dashboard
    aluno: Optional[AlunoResponse] = None 
    dispositivo: Optional[DispositivoResponse] = None

    model_config = ConfigDict(from_attributes=True)


class AlunoEnrollado(BaseModel):
    """
    Resposta de sucesso do POST /access/enroll (HTTP 201).
    Contém apenas o necessário para o app confirmar o cadastro.
    """
    id_aluno: int
    matricula: str
    nome_completo: str
    mensagem: str = "Aluno cadastrado com sucesso. Vetor facial indexado no banco."

    model_config = ConfigDict(from_attributes=False)


class ErroDuplicata(BaseModel):
    """
    Resposta de conflito de matrícula ou biométrico (HTTP 409).
    Formato definido pelo contrato OpenAPI v1.2.0.
    """
    erro: str
    campo: str
    valor_conflitante: str

   # ==========================================
# 5. SCHEMAS DA ROTA /access/verify
# ==========================================

class AcessoLiberado(BaseModel):
    """
    Resposta HTTP 200 do POST /access/verify.
    O ESP32 usa o status 200 para acionar o relé imediatamente.
    """
    status: str = "liberado"
    nome: str
    matricula: str
    tipo_vinculo: str

    model_config = ConfigDict(from_attributes=False)


class AcessoBloqueado(BaseModel):
    """
    Resposta HTTP 403 do POST /access/verify.
    O campo codigo_motivo é lido pelo ESP32 e pelo app do segurança.
    """
    status: str = "bloqueado"
    motivo: str
    codigo_motivo: str  # ROSTO_NAO_RECONHECIDO | BLOQUEIO_ADMINISTRATIVO | BLOCO_NAO_PERMITIDO

    model_config = ConfigDict(from_attributes=False) 