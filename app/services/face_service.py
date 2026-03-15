import face_recognition
import numpy as np
from PIL import Image
import io
import logging

class LowQualityImageError(Exception):
    pass

def extract_face_vector(image_bytes: bytes) -> np.ndarray:
    """Recebe JPEG em bytes. Retorna vetor float32[128]."""
    try:
        pil_image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception as e:
        raise ValueError(f'Imagem inválida: {e}')
    
    img_array = np.array(pil_image)
    face_locations = face_recognition.face_locations(img_array, model='hog')
    
    if not face_locations:
        raise ValueError('Nenhuma face detectada na imagem.')
        
    encodings = face_recognition.face_encodings(img_array, face_locations)
    if not encodings:
        raise LowQualityImageError('Qualidade insuficiente para extração do vetor.')
        
    vector = encodings[0].astype(np.float32)
    assert vector.shape == (128,), f'Shape inesperado: {vector.shape}'
    return vector

def vector_to_blob(vector: np.ndarray) -> bytes:
    """Serializa vetor float32[128] para bytes (BLOB no SQLite)."""
    return vector.tobytes()

def blob_to_vector(blob: bytes) -> np.ndarray:
    """Desserializa BLOB do SQLite para vetor float32[128]."""
    return np.frombuffer(blob, dtype=np.float32)