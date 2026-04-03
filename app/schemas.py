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
# 3. SCHEMAS DE DISPOSITIVOS E EVENTOS (Dashboard)
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