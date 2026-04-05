import logging
from sqlalchemy.orm import Session
from app import models

logger = logging.getLogger(__name__)

def gravar_evento(db: Session, id_aluno: int, id_dispositivo: int, resultado: str, codigo_motivo: str, distancia: float):
    try:
        # Criamos uma nova sessão local para a task se necessário, 
        # ou usamos a passada se garantirmos que não foi fechada.
        evento = models.EventoAcesso(
            id_aluno=id_aluno,
            id_dispositivo=id_dispositivo,
            resultado=resultado,
            codigo_motivo=codigo_motivo,
            distancia_faiss=distancia
        )
        db.add(evento)
        db.commit()
    except Exception as e:
        logger.error(f"Falha ao gravar log de acesso: {e}")
        db.rollback()

def upload_firebase(image_bytes: bytes, aluno: models.Aluno, dispositivo: models.Dispositivo):
    try:
        # Aqui entra a lógica que você e o João integrarem com o Firebase Storage
        # Por enquanto, simule o sucesso para não travar o log
        logger.info(f"Foto de {aluno.nome_completo} enviada para o storage do bloco {dispositivo.bloco}")
    except Exception as e:
        logger.error(f"Erro no upload Firebase: {e}")