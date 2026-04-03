from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base

class Aluno(Base):
    __tablename__ = "alunos"

    id_aluno = Column(Integer, primary_key=True, index=True)
    matricula = Column(String(20), unique=True, nullable=False, index=True)
    nome_completo = Column(String(255), nullable=False)
    curso = Column(String(100), nullable=False)
    
    # Restrições de Enum (GRADUACAO, POS_GRADUACAO, etc.) serão validadas no Pydantic
    tipo_vinculo = Column(String(50), nullable=False) 
    turno = Column(String(20), nullable=False)
    status_acesso = Column(String(20), default="ATIVO")
    
    # 🌟 A Mágica do pgvector: 128 dimensões da nossa IA
    vetor_128d = Column(Vector(128)) 
    
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos (Navegação bidirecional)
    overrides = relationship("OverrideAcesso", back_populates="aluno", cascade="all, delete-orphan")
    eventos = relationship("EventoAcesso", back_populates="aluno")


class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id_dispositivo = Column(Integer, primary_key=True, index=True)
    api_key = Column(String(100), unique=True, nullable=False)
    localizacao = Column(String(150), nullable=False)
    bloco = Column(String(50), nullable=False)
    mac_address = Column(String(17), unique=True)
    is_ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    eventos = relationship("EventoAcesso", back_populates="dispositivo")


class RegraBlocoVinculo(Base):
    __tablename__ = "regras_bloco_vinculo"

    id_regra = Column(Integer, primary_key=True, index=True)
    tipo_vinculo = Column(String(50), nullable=False)
    bloco = Column(String(50), nullable=False)
    permitido = Column(Boolean, default=True)


class OverrideAcesso(Base):
    __tablename__ = "overrides_acesso"

    id_override = Column(Integer, primary_key=True, index=True)
    id_aluno = Column(Integer, ForeignKey("alunos.id_aluno", ondelete="CASCADE"), nullable=False)
    bloco = Column(String(50), nullable=False)
    tipo_override = Column(String(20), nullable=False) # PERMITIR ou BLOQUEAR
    motivo = Column(Text)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    aluno = relationship("Aluno", back_populates="overrides")


class EventoAcesso(Base):
    __tablename__ = "eventos_acesso"

    id_evento = Column(Integer, primary_key=True, index=True)
    # SET NULL permite manter o histórico mesmo se o aluno for apagado do banco
    id_aluno = Column(Integer, ForeignKey("alunos.id_aluno", ondelete="SET NULL"), nullable=True)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id_dispositivo"), nullable=True)
    
    resultado = Column(String(20), nullable=False) # LIBERADO, BLOQUEADO, DESCONHECIDO
    codigo_motivo = Column(String(50))
    distancia_ia = Column(Float) # Distância vetorial calculada na hora do acesso
    
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    aluno = relationship("Aluno", back_populates="eventos")
    dispositivo = relationship("Dispositivo", back_populates="eventos")