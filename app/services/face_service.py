# app/services/face_service.py
import face_recognition
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)


class LowQualityImageError(Exception):
    """Levantada quando a imagem é válida mas tem qualidade insuficiente para extração."""
    pass


def extract_face_vector(image_bytes: bytes) -> np.ndarray:
    """
    Recebe bytes de uma imagem JPEG/PNG.
    Retorna um vetor float32 de 128 dimensões representando o rosto.

    Raises:
        ValueError: imagem corrompida, sem rosto, ou múltiplos rostos.
        LowQualityImageError: imagem detectável mas escura demais para ser precisa.
    """
    # 1. Tenta abrir a imagem
    try:
        pil_image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception as e:
        raise ValueError(f'Imagem inválida ou corrompida: {e}')

    img_array = np.array(pil_image)

    # 2. Validação de brilho (imagem totalmente escura não gera vetor confiável)
    brilho_medio = np.mean(img_array)
    if brilho_medio < 40:
        raise LowQualityImageError(
            f'Imagem muito escura (brilho médio: {brilho_medio:.1f}/255). '
            'Melhore a iluminação e tente novamente.'
        )

    # 3. Detecta localização dos rostos na imagem
    face_locations = face_recognition.face_locations(img_array, model='hog')

    if not face_locations:
        raise ValueError(
            'Nenhum rosto detectado na imagem. '
            'Aproxime-se da câmera e garanta boa iluminação frontal.'
        )

    if len(face_locations) > 1:
        raise ValueError(
            f'Múltiplos rostos detectados ({len(face_locations)}). '
            'Apenas uma pessoa é permitida por vez na catraca.'
        )

    # 4. Extrai o vetor de 128 dimensões do rosto encontrado
    encodings = face_recognition.face_encodings(img_array, face_locations)

    if not encodings:
        raise LowQualityImageError(
            'Rosto detectado, mas qualidade insuficiente para extração segura do vetor. '
            'Tente em resolução SVGA (800x600) ou melhore a iluminação.'
        )

    vector = encodings[0].astype(np.float32)

    # Garantia de contrato: vetor deve ter exatamente 128 dimensões
    assert vector.shape == (128,), f'Shape inesperado do vetor: {vector.shape}'

    logger.debug(f'Vetor extraído com sucesso. Shape: {vector.shape}, dtype: {vector.dtype}')
    return vector


def vector_to_blob(vector: np.ndarray) -> bytes:
    """Serializa vetor float32[128] para bytes brutos (para armazenamento BLOB)."""
    return vector.tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    """Desserializa bytes brutos de volta para vetor float32[128]."""
    return np.frombuffer(blob, dtype=np.float32)