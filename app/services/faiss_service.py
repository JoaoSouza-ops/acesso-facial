import os
import faiss
import numpy as np
from typing import Optional, Tuple
import threading
import logging


# Caminho do índice (ajuste se necessário)
INDEX_PATH = "vector_index.index"
dimension = 128
index = faiss.IndexFlatL2(dimension)

def add_vector(vetor_np, id_aluno):
    # O erro estava aqui: usaremos 'vetor_np' que é o nome do parâmetro
    ids_np = np.array([id_aluno]).astype('int64')
    
    # Criamos o IndexIDMap se não existir para aceitar IDs personalizados
    global index
    if not isinstance(index, faiss.IndexIDMap):
        index = faiss.IndexIDMap(index)
    
    # Adiciona ao motor de busca
    index.add_with_ids(vetor_np, ids_np)
    
    # Salva o backup no disco (Disaster Recovery)
    faiss.write_index(index, INDEX_PATH)
    print(f"--- IA: Vetor do aluno {id_aluno} salvo com sucesso! ---")

def load_index():
    """
    Tenta carregar o índice do disco no arranque do servidor.
    Se não existir, mantém o _index limpo (ou cria um novo, dependendo do teu setup).
    """
    global _index
    with _lock:
        if os.path.exists(INDEX_PATH):
            print(f"[FAISS] A carregar índice do disco: {INDEX_PATH}")
            _index = faiss.read_index(INDEX_PATH)
        else:
            print("[FAISS] Nenhum ficheiro encontrado. A iniciar com índice vazio.")
            # Assume-se que a tua inicialização padrão (ex: IndexFlatL2) 
            # já ocorre na variável _index noutra parte do teu código.

def save_index():
    """
    Guarda o estado atual do índice (RAM) para o disco.
    Deve ser chamado de forma assíncrona ou após cada novo registo.
    """
    with _lock:
        if _index is not None:
            faiss.write_index(_index, INDEX_PATH)
            print(f"[FAISS] Snapshot gravado com sucesso em {INDEX_PATH}.")

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


def search_vector(vector: np.ndarray, threshold: float = 0.6) -> Tuple[Optional[int], float]:
    with _lock:
        if _index is None or _index.ntotal == 0:
            return None, float('inf')
        distances, indices = _index.search(vector.reshape(1, DIMENSION).astype(np.float32), k=1)
        dist, idx = float(distances[0][0]), int(indices[0][0])
        return (idx, dist) if dist <= threshold else (None, dist)

def get_total() -> int:
    return 0 if _index is None else _index.ntotal

# Inicializa o índice carregando do disco (se existir) no arranque do módulo
load_index()