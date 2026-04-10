# app/services/faiss_service.py
"""
Serviço de índice vetorial FAISS — usado em testes offline e benchmarks.
Em produção, a busca vetorial usa pgvector (PostgreSQL).
"""
import faiss
import numpy as np
import threading
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Estado global do índice (singleton) ──────────────────────────────────────
_index: Optional[faiss.IndexFlatL2] = None
_lock = threading.Lock()
DIMENSION = 128


def initialize_index(vetores: list, ids: list) -> None:
    """
    (Re)inicializa o índice FAISS em memória.

    Args:
        vetores: lista de arrays float32[128]. Pode ser vazia.
        ids:     lista de IDs correspondentes (não usados pelo FAISS, apenas para referência).
    """
    global _index
    with _lock:
        _index = faiss.IndexFlatL2(DIMENSION)
        if vetores:
            matriz = np.array(vetores, dtype=np.float32)
            _index.add(matriz)
        logger.info(f'FAISS inicializado com {_index.ntotal} vetores.')


def add_vector(vector: np.ndarray) -> int:
    """
    Adiciona um vetor ao índice.

    Returns:
        Posição 0-based do vetor no índice (id_FAISS).
    """
    global _index
    with _lock:
        if _index is None:
            raise RuntimeError('FAISS não inicializado. Chame initialize_index() primeiro.')
        _index.add(vector.reshape(1, DIMENSION).astype(np.float32))
        return _index.ntotal - 1


def search_vector(vector: np.ndarray, threshold: float = 0.6) -> Tuple[Optional[int], float]:
    """
    Busca o vizinho mais próximo no índice.

    Returns:
        (id_FAISS, distancia) se distancia <= threshold, senão (None, distancia).
    """
    with _lock:
        if _index is None or _index.ntotal == 0:
            return None, float('inf')

        distances, indices = _index.search(
            vector.reshape(1, DIMENSION).astype(np.float32), k=1
        )
        dist = float(distances[0][0])
        idx  = int(indices[0][0])

        if dist <= threshold:
            return idx, dist
        return None, dist


def get_total() -> int:
    """Retorna o número de vetores no índice."""
    if _index is None:
        return 0
    return _index.ntotal

