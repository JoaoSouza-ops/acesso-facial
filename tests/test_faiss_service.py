import numpy as np
from app.services import faiss_service

def setup_function(): 
    faiss_service._index = None

def test_inicializa_vazio():
    faiss_service.initialize_index([], [])
    assert faiss_service.get_total() == 0

def test_adiciona_e_recupera():
    faiss_service.initialize_index([], [])
    v = np.random.rand(128).astype(np.float32)
    faiss_service.add_vector(v)
    idx, dist = faiss_service.search_vector(v, threshold=0.6)
    assert idx == 0 and dist < 0.001

def test_desconhecido_retorna_none():
    faiss_service.initialize_index([], [])
    faiss_service.add_vector(np.random.rand(128).astype(np.float32))
    idx, _ = faiss_service.search_vector(np.random.rand(128).astype(np.float32), threshold=0.001)
    assert idx is None

def test_indice_cresce():
    faiss_service.initialize_index([], [])
    for _ in range(5): 
        faiss_service.add_vector(np.random.rand(128).astype(np.float32))
    assert faiss_service.get_total() == 5