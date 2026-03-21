from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# --- Enums para Validação ---

class TipoVinculo(str, Enum):
    REGULAR = "Regular"
    BOLSISTA = "Bolsista"
    EGRESSO = "Egresso"
    DOCENTE = "Docente"
    ADMINISTRATIVO = "Administrativo"

class Turno(str, Enum):
    MATUTINO = "Matutino"
    VESPERTINO = "Vespertino"
    NOTURNO = "Noturno"
    INTEGRAL = "Integral"

# --- Schemas de Requisição (Input) ---

class EnrollRequest(BaseModel):
    matricula: str = Field(..., example="202300123")
    nome_completo: str = Field(..., example="Ian Araujo dos Santos")
    curso: str = Field(..., example="Engenharia da Computação")
    tipo_vinculo: TipoVinculo
    turno: Turno
    vetor_128d: List[float] = Field(..., min_items=128, max_items=128)

# --- Schemas de Resposta (Output) ---

class AlunoEnrollado(BaseModel):
    id_aluno: int
    matricula: str
    mensagem: str = "Aluno cadastrado com sucesso"

class AcessoLiberado(BaseModel):
    id_evento: int
    id_aluno: int
    nome_aluno: str
    resultado: str = "Liberado"
    mensagem: str = "Acesso autorizado"
    ocorrido_em: datetime

class AcessoBloqueado(BaseModel):
    id_evento: int
    id_aluno: Optional[int] = None
    resultado: str = "Negado"
    codigo_motivo: str 
    mensagem: str
    ocorrido_em: datetime

# --- Schemas de Erro ---

class ErroPadrao(BaseModel):
    detalhe: str = Field(..., example="Ocorreu um erro interno no servidor")

class ErroDuplicata(BaseModel):
    detalhe: str = Field(..., example="Matrícula já cadastrada no sistema")