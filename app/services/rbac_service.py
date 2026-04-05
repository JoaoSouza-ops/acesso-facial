from sqlalchemy.orm import Session
from app import models
from typing import Tuple


def validar_regras_acesso(id_aluno: int, id_dispositivo: int, db: Session) -> Tuple[bool, str]:
    """4 regras em sequência. Primeira que disparar encerra o fluxo. Fail-Secure."""
    aluno = db.query(models.Aluno).filter_by(id_aluno=id_aluno).first()
    disp  = db.query(models.Dispositivo).filter_by(id_dispositivo=id_dispositivo).first()
    if not aluno or not disp: return False, 'ERRO_INTERNO'
    bloco = disp.bloco
    # Regra 1
    if aluno.status_acesso == 'BLOQUEADO': return False, 'BLOQUEIO_ADMINISTRATIVO'
    # Regra 2
    if db.query(models.OverrideAcesso).filter_by(
            id_aluno=id_aluno, bloco=bloco, tipo_override='BLOQUEAR').first():
        return False, 'BLOCO_NAO_PERMITIDO'
    # Regra 3
    if db.query(models.OverrideAcesso).filter_by(
            id_aluno=id_aluno, bloco=bloco, tipo_override='PERMITIR').first():
        return True, ''
    # Regra 4 (Fail-Secure: sem regra explícita → nega)
    if db.query(models.RegrasBlocoVinculo).filter_by(
            tipo_vinculo=aluno.tipo_vinculo, bloco=bloco).first():
        return True, ''
    return False, 'BLOCO_NAO_PERMITIDO'

