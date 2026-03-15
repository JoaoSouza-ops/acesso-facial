import pytest, numpy as np 
from pathlib import Path 
from app.services.face_service import ( 
    extract_face_vector, vector_to_blob, blob_to_vector, LowQualityImageError 
) 

FIXTURES = Path('tests/fixtures') 

def test_extrai_vetor_de_foto_valida(): 
    v = extract_face_vector((FIXTURES / 'foto_joao1.jpg').read_bytes()) 
    assert v.shape == (128,) and v.dtype == np.float32 

def test_levanta_erro_sem_face(): 
    with pytest.raises(ValueError): 
        extract_face_vector((FIXTURES / 'paisagem.jpg').read_bytes()) 

def test_round_trip_serializacao(): 
    v = extract_face_vector((FIXTURES / 'foto_joao1.jpg').read_bytes()) 
    assert np.allclose(v, blob_to_vector(vector_to_blob(v)), atol=1e-6) 

def test_mesma_foto_mesmo_vetor(): 
    foto = (FIXTURES / 'foto_joao1.jpg').read_bytes() 
    assert np.allclose(extract_face_vector(foto), extract_face_vector(foto), atol=1e-6)