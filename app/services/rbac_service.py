# app/services/rbac_service.py
"""
Motor de Regras RBAC — Controle de Acesso Baseado em Função + Overrides Individuais.

Princípio de design (Robert C. Martin, Clean Architecture, Cap. 8):
  Este módulo é completamente isolado da IA. Recebe apenas IDs e consulta
  o banco. Para adicionar uma nova regra no futuro, basta inserir um novo
  bloco IF aqui — sem tocar em face_service, vision_service ou nas rotas.

Referência: NIST SP 800-162, Seção 4.2 — Attribute-Based Access Control.
"""
import logging
from typing import Tuple
from sqlalchemy.orm import Session
from app import models

logger = logging.getLogger(__name__)


def validar_regras_acesso(
    id_aluno: int,
    id_dispositivo: int,
    db: Session
) -> Tuple[bool, str]:
    """
    Executa as 4 regras RBAC em sequência.
    A primeira regra que disparar encerra o fluxo imediatamente.

    Args:
        id_aluno:       PK do aluno identificado pela IA.
        id_dispositivo: PK da catraca que originou a requisição.
        db:             Sessão ativa do banco de dados.

    Returns:
        (permitido: bool, codigo_motivo: str)
        - (True,  '')                        → acesso liberado
        - (False, 'BLOQUEIO_ADMINISTRATIVO') → aluno bloqueado pela secretaria
        - (False, 'BLOCO_NAO_PERMITIDO')     → vínculo sem permissão neste bloco
        - (False, 'ERRO_INTERNO')            → aluno ou dispositivo não encontrado
    """

    # ── Carrega os dados necessários ─────────────────────────────────────────
    aluno = db.query(models.Aluno).filter(
        models.Aluno.id_aluno == id_aluno
    ).first()

    dispositivo = db.query(models.Dispositivo).filter(
        models.Dispositivo.id_dispositivo == id_dispositivo
    ).first()

    if not aluno or not dispositivo:
        logger.error(
            f"RBAC: entidade não encontrada — "
            f"id_aluno={id_aluno}, id_dispositivo={id_dispositivo}"
        )
        return False, 'ERRO_INTERNO'

    bloco = dispositivo.bloco

    logger.debug(
        f"RBAC iniciado: aluno={aluno.nome_completo} "
        f"tipo_vinculo={aluno.tipo_vinculo} "
        f"bloco={bloco}"
    )

    # ── Regra 1: Bloqueio Administrativo ─────────────────────────────────────
    # A secretaria pode bloquear qualquer aluno independente do bloco.
    if aluno.status_acesso == 'BLOQUEADO':
        logger.info(
            f"RBAC Regra 1 disparou: {aluno.nome_completo} "
            f"tem status BLOQUEADO."
        )
        return False, 'BLOQUEIO_ADMINISTRATIVO'

    # ── Regra 2: Override Individual — BLOQUEAR ───────────────────────────────
    # Um aluno pode ter acesso negado em um bloco específico mesmo que sua
    # categoria normalmente permita.
    override_bloquear = db.query(models.OverrideAcesso).filter(
        models.OverrideAcesso.id_aluno == id_aluno,
        models.OverrideAcesso.bloco == bloco,
        models.OverrideAcesso.tipo_override == 'BLOQUEAR'
    ).first()

    if override_bloquear:
        logger.info(
            f"RBAC Regra 2 disparou: override BLOQUEAR para "
            f"{aluno.nome_completo} no bloco {bloco}."
        )
        return False, 'BLOCO_NAO_PERMITIDO'

    # ── Regra 3: Override Individual — PERMITIR ───────────────────────────────
    # Um aluno pode ter acesso liberado em um bloco que normalmente seria negado.
    # Exemplo: FUNCIONARIO com acesso ao BLOCO_AULAS (bolsista, técnico de TI).
    override_permitir = db.query(models.OverrideAcesso).filter(
        models.OverrideAcesso.id_aluno == id_aluno,
        models.OverrideAcesso.bloco == bloco,
        models.OverrideAcesso.tipo_override == 'PERMITIR'
    ).first()

    if override_permitir:
        logger.info(
            f"RBAC Regra 3 disparou: override PERMITIR para "
            f"{aluno.nome_completo} no bloco {bloco}."
        )
        return True, ''

    # ── Regra 4: Regra Padrão do Vínculo (Fail-Secure) ───────────────────────
    # Consulta a tabela de regras configurada na seed.
    # Se não existir nenhuma regra para esta combinação, o acesso é NEGADO.
    # "Sem regra explícita = nega" é o princípio Fail-Secure.
    regra_padrao = db.query(models.RegraBlocoVinculo).filter(
        models.RegraBlocoVinculo.tipo_vinculo == aluno.tipo_vinculo,
        models.RegraBlocoVinculo.bloco == bloco
    ).first()

    if regra_padrao:
        logger.info(
            f"RBAC Regra 4 disparou: regra padrão libera "
            f"{aluno.tipo_vinculo} no bloco {bloco}."
        )
        return True, ''

    logger.info(
        f"RBAC Regra 4 — Fail-Secure: nenhuma regra para "
        f"{aluno.tipo_vinculo} no bloco {bloco}. Acesso negado."
    )
    return False, 'BLOCO_NAO_PERMITIDO'