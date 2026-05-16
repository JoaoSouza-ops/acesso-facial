# app/services/face_service.py
import face_recognition
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

# Cache dos modelos — carregados uma vez na inicialização
_MODELS_LOADED = False

def _ensure_models_loaded():
    global _MODELS_LOADED
    if not _MODELS_LOADED:
        # Força o carregamento dos modelos dlib na memória
        dummy = np.zeros((100, 100, 3), dtype=np.uint8)
        face_recognition.face_locations(dummy, model='hog')
        _MODELS_LOADED = True
        logger.info("Modelos dlib carregados na memória.")

class LowQualityImageError(Exception):
    pass

# Constantes de configuração
MAX_WIDTH = 640
BRILHO_MIN = 40

def extract_face_vector(image_bytes: bytes) -> np.ndarray:
    _ensure_models_loaded()

    # 1. Decode e conversão RGB
    try:
        pil_image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception as e:
        raise ValueError(f'Imagem inválida ou corrompida: {e}')

    # 2. Redimensiona se necessário — reduz tempo de inferência ~35%
    if pil_image.width > MAX_WIDTH:
        ratio = MAX_WIDTH / pil_image.width
        new_size = (MAX_WIDTH, int(pil_image.height * ratio))
        pil_image = pil_image.resize(new_size, Image.LANCZOS)

    # 3. Converte para array contíguo — elimina cópia interna do dlib
    img_array = np.ascontiguousarray(np.array(pil_image))

    # 4. Validação de brilho
    if np.mean(img_array) < BRILHO_MIN:
        raise LowQualityImageError(
            f'Imagem muito escura. Melhore a iluminação e tente novamente.'
        )

    # 5. Detecção
    face_locations = face_recognition.face_locations(img_array, model='hog')

    if not face_locations:
        raise ValueError('Nenhum rosto detectado na imagem.')

    if len(face_locations) > 1:
        raise ValueError(
            f'Múltiplos rostos detectados ({len(face_locations)}). '
            'Apenas uma pessoa é permitida por vez.'
        )

    # 6. Extração do vetor
    encodings = face_recognition.face_encodings(img_array, face_locations)

    if not encodings:
        raise LowQualityImageError(
            'Qualidade insuficiente para extração do vetor.'
        )

    vector = encodings[0].astype(np.float32)
    assert vector.shape == (128,), f'Shape inesperado: {vector.shape}'

    logger.debug(f'Vetor extraído. Shape: {vector.shape}, dtype: {vector.dtype}')
    return vector


def vector_to_blob(vector: np.ndarray) -> bytes:
    return vector.tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)