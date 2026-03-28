# app/services/vision_service.py
import face_recognition
import numpy as np
import io
from PIL import Image

def extrair_vetor_da_imagem(imagem_bytes: bytes) -> np.ndarray:
    """
    Recebe os bytes de uma foto JPG/PNG, localiza o rosto e retorna o vetor de 128 dimensões.
    """
    try:
        # 1. Converte os bytes puros recebidos via HTTP em uma imagem legível
        imagem_pillow = Image.open(io.BytesIO(imagem_bytes)).convert('RGB')
        imagem_np = np.array(imagem_pillow)

        # 2. Localiza onde estão os rostos na foto (as coordenadas do quadrado em volta do rosto)
        rostos_encontrados = face_recognition.face_locations(imagem_np)

        # 3. Regras de Negócio de Segurança (Catraca do Smartbuild)
        if len(rostos_encontrados) == 0:
            raise ValueError("Nenhum rosto detectado na imagem. Chegue mais perto da câmera.")
        
        if len(rostos_encontrados) > 1:
            raise ValueError("Múltiplos rostos detectados. Apenas uma pessoa permitida por vez na catraca.")

        # 4. Extrai a "assinatura matemática" (o vetor de 128d) do único rosto válido
        codificacoes = face_recognition.face_encodings(imagem_np, known_face_locations=rostos_encontrados)
        vetor_128d = codificacoes[0]

        # 5. Formata exatamente como o FAISS precisa (float32)
        return np.array(vetor_128d, dtype=np.float32)

    except Exception as e:
        # Repassa o erro para a rota principal lidar com ele (ex: retornar um HTTP 400)
        raise ValueError(f"Erro ao processar a imagem: {str(e)}")