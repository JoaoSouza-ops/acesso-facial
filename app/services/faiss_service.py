import faiss
import numpy as np
import threading
import logging
from typing import Optional, Tuple

_index: Optional[faiss.IndexFlatL2] = None
_lock = threading.Lock()
DIMENSION = 128
logger = logging.getLogger(__name__)

def initialize_index(vetores: list, ids: list) -> None:
    global _index
    with _lock:
        _index = faiss.IndexFlatL2(DIMENSION)
        if vetores:
            _index.add(np.array(vetores, dtype=np.float32))
        logger.info(f'FAISS: {_index.ntotal} vetores carregados.')

def add_vector(vector: np.ndarray) -> int:
    global _index
    with _lock:
        if _index is None:
            raise RuntimeError('FAISS não inicializado.')
        _index.add(vector.reshape(1, DIMENSION).astype(np.float32))
        return _index.ntotal - 1

def search_vector(vector: np.ndarray, threshold: float = 0.6) -> Tuple[Optional[int], float]:
    with _lock:
        if _index is None or _index.ntotal == 0:
            return None, float('inf')
        distances, indices = _index.search(vector.reshape(1, DIMENSION).astype(np.float32), k=1)
        dist, idx = float(distances[0][0]), int(indices[0][0])
        return (idx, dist) if dist <= threshold else (None, dist)

def get_total() -> int:
    return 0 if _index is None else _index.ntotal