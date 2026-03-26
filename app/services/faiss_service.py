import os
import faiss
import numpy as np
from typing import Optional, Tuple
import threading
import logging


# Caminho do índice (ajuste se necessário)
INDEX_PATH = "vector_index.index"
DIMENSION = 128
index = faiss.IndexFlatL2(DIMENSION)


# Tenta carregar, se não existir, cria um do zero
if os.path.exists(INDEX_PATH):
    _index = faiss.read_index(INDEX_PATH)
    print("--- IA: Índice carregado do disco ---")
else:
    # Criamos o FlatL2 e envolvemos no IDMap para aceitar IDs personalizados
    _index = faiss.IndexIDMap(faiss.IndexFlatL2(DIMENSION))
    print("--- IA: Novo índice criado do zero ---")

def add_vector(vector: np.ndarray, id_aluno: int):
    with _lock:
        # Garante o formato correto (1, 128)
        vector_np = vector.reshape(1, DIMENSION).astype(np.float32)
        ids_np = np.array([id_aluno]).astype('int64')
        
        # Adiciona ao índice
        _index.add_with_ids(vector_np, ids_np)
        
        # SALVA NO DISCO IMEDIATAMENTE (Importante!)
        faiss.write_index(_index, INDEX_PATH)
        print(f"--- IA: Vetor do aluno {id_aluno} salvo fisicamente em {INDEX_PATH} ---")

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
        
        # O reshape garante que o vetor esteja no formato (1, 128)
        distances, indices = _index.search(vector.reshape(1, DIMENSION).astype(np.float32), k=1)
        dist, idx = float(distances[0][0]), int(indices[0][0])
        
        # Para CALIBRAÇÃO: Retornamos o ID (se bater o threshold) E a distância real
        # Se dist > threshold, retornamos None no ID, mas mantemos o valor de dist para estudo
        id_resultado = idx if dist <= threshold else None
        return id_resultado, dist

def get_total() -> int:
    return 0 if _index is None else _index.ntotal


# Inicializa o índice carregando do disco (se existir) no arranque do módulo
load_index()
