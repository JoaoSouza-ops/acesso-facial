from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, Boolean, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Aluno(Base):
    __tablename__ = "alunos"

    id_aluno = Column(Integer, primary_key=True, index=True)
    matricula = Column(String(20), unique=True, nullable=False, index=True)
    nome_completo = Column(String(255), nullable=False)
    curso = Column(String(100))
    tipo_vinculo = Column(String(50)) 
    turno = Column(String(20))       
    status_acesso = Column(String(20), default="Ativo")
    vetor_128d = Column(LargeBinary) # armazena o modelo facial
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Aluno(nome='{self.nome_completo}', matricula='{self.matricula}')>"

class Dispositivo(Base):
    __tablename__ = "dispositivos"

    id_dispositivo = Column(Integer, primary_key=True, index=True)
    api_key = Column(String(64), unique=True, nullable=False)
    mac_address = Column(String(17), unique=True)
    localizacao = Column(String(100))
    bloco = Column(String(50), index=True) 
    ativo = Column(Boolean, default=True)
    cadastrado_em = Column(DateTime(timezone=True), server_default=func.now())

class RegrasBlocoVinculo(Base):
    __tablename__ = "regras_bloco_vinculo"

    id_regra = Column(Integer, primary_key=True, index=True)
    tipo_vinculo = Column(String(50), nullable=False)
    bloco = Column(String(50), nullable=False)

class OverrideAcesso(Base):
    __tablename__ = "overrides_acesso"

    id_override = Column(Integer, primary_key=True, index=True)
    id_aluno = Column(Integer, ForeignKey("alunos.id_aluno"), nullable=False)
    bloco = Column(String(50), nullable=False)
    tipo_override = Column(String(20))
    motivo = Column(String(255))
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

class EventoAcesso(Base):
    __tablename__ = "eventos_acesso"

    id_evento = Column(Integer, primary_key=True, index=True)
    id_aluno = Column(Integer, ForeignKey("alunos.id_aluno"), nullable=True)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id_dispositivo"), nullable=False)
    
    resultado = Column(String(20))      
    codigo_motivo = Column(String(50))  
    distancia_faiss = Column(Float)     
    ocorrido_em = Column(DateTime(timezone=True), server_default=func.now())