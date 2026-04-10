import os
import numpy as np
# Importamos o serviço que acabou de criar
from app.services.vision_service import extrair_vetor_da_imagem

def executar_teste_visao():
    nome_ficheiro = "foto_teste.jpg"
    
    print(f"--- 🧪 INICIANDO TESTE DO VISION SERVICE ---")
    
    # 1. Verifica se a foto existe na pasta
    if not os.path.exists(nome_ficheiro):
        print(f"❌ ERRO: Não encontrei o ficheiro '{nome_ficheiro}'.")
        print("Por favor, coloque uma foto com o seu rosto na mesma pasta deste script.")
        return

    # 2. Lê a foto como bytes (exatamente como a API do FastAPI vai receber)
    print(f"📷 A ler os bytes da imagem '{nome_ficheiro}'...")
    with open(nome_ficheiro, "rb") as f:
        imagem_bytes = f.read()

    # 3. Passa os bytes para o nosso "Tradutor"
    print("🧠 A processar a imagem através da rede neural (Dlib/face_recognition)...")
    
    try:
        vetor_resultado = extrair_vetor_da_imagem(imagem_bytes)
        
        # 4. Resultados do Teste
        print("\n✅ SUCESSO! Rosto localizado e traduzido.")
        print(f"📐 Dimensões do vetor: {vetor_resultado.shape} (Deve ser 128,)")
        print(f"📊 Tipo de dado: {vetor_resultado.dtype} (Deve ser float32 para o FAISS)")
        print(f"🔢 Amostra dos 5 primeiros números da sua assinatura facial:")
        print(vetor_resultado[:5])
        
    except ValueError as e:
        # Aqui vamos ver as nossas regras anti-fraude a funcionar (ex: zero rostos ou múltiplos rostos)
        print(f"\n🛡️ REGRA DE NEGÓCIO ACIONADA: {e}")
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")

if __name__ == "__main__":
    executar_teste_visao()