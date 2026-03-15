import pytest
import numpy as np
from pathlib import Path
from app.services.face_service import extract_face_vector, LowQualityImageError
from app.services import faiss_service

FIXTURES = Path('tests/fixtures')

def test_erro_foto_totalmente_escura():
    """Garante que fotos sem informação visual levantem erro em vez de crashar."""
    # Criando um array de bytes que representa uma imagem preta
    foto_preta = np.zeros((100, 100, 3), dtype=np.uint8).tobytes()
    with pytest.raises(ValueError):
        extract_face_vector(foto_preta)

def test_comportamento_multiplas_faces():
    """
    Verifica se o sistema lida com mais de uma face. 
    O face_recognition por padrão pega a primeira, mas o sistema deve ser consistente.
    """
    caminho = FIXTURES / 'duas_faces.jpeg'
    if caminho.exists():
        vetor = extract_face_vector(caminho.read_bytes())
        assert vetor.shape == (128,)
    else:
        pytest.skip("Fixture 'duas_faces.jpg' não encontrada.")

def test_extração_com_foto_real_escura():
    """Testa se a IA identifica que a imagem real não tem qualidade suficiente."""
    caminho = FIXTURES / 'baixa_luminosidade2.jpeg'
    if caminho.exists():
        # DEBUG: Verificando o brilho real da foto para entender o motivo do erro
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(caminho.read_bytes()))
        print(f"\nDEBUG: O brilho real da foto é: {np.mean(np.array(img))}")
        with pytest.raises((ValueError, LowQualityImageError)):
            extract_face_vector(caminho.read_bytes())
    else:
        pytest.skip("Ficheiro 'baixa_luminosidade2.jpeg' não encontrado em fixtures.")

def test_distancia_faiss_foto_borrada():
    """
    Testa se uma foto borrada da mesma pessoa (João) 
    resulta numa distância maior que a foto nítida, validando o Threshold.
    """
    faiss_service.initialize_index([], [])
    
    # Foto nítida (Cadastro)
    vetor_nitido = extract_face_vector((FIXTURES / 'foto_joao1.jpg').read_bytes())
    faiss_service.add_vector(vetor_nitido)
    
    # Foto borrada (Verificação)
    caminho_borrada = FIXTURES / 'borrada.jpeg'
    if caminho_borrada.exists():
        vetor_borrado = extract_face_vector(caminho_borrada.read_bytes())
        idx, dist = faiss_service.search_vector(vetor_borrado, threshold=0.6)
        
        # A distância de uma foto ruim deve ser maior que uma foto boa
        _, dist_perfeita = faiss_service.search_vector(vetor_nitido, threshold=0.6)
        assert dist > dist_perfeita
    else:
        pytest.skip("Fixture 'borrada.jpeg' não encontrada.")