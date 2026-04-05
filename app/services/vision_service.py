# app/services/vision_service.py
"""
Adaptador de compatibilidade.
O main.py usa este módulo, mas toda a lógica de IA vive em face_service.py.
Isso garante que os testes e o backend apontem para a mesma implementação.
"""
from app.services.face_service import (
    extract_face_vector,
    vector_to_blob,
    blob_to_vector,
    LowQualityImageError,
)


def extrair_vetor_da_imagem(imagem_bytes: bytes):
    """
    Wrapper de compatibilidade chamado pelo main.py.
    Delega para extract_face_vector() do face_service.

    Raises:
        ValueError: se não encontrar rosto ou a imagem for inválida.
        LowQualityImageError: se a imagem for escura demais.
    """
    return extract_face_vector(imagem_bytes)