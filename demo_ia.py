import sys
from app.services import face_service, faiss_service

# Cores para deixar o terminal bonito na apresentação
VERDE = '\033[92m'
VERMELHO = '\033[91m'
AMARELO = '\033[93m'
RESET = '\033[0m'

def demonstrar_cenario(nome_cenario, caminho_imagem, id_esperado=None):
    print(f"\n{AMARELO}--- Testando: {nome_cenario} ---{RESET}")
    print(f"Simulando foto recebida do ESP32-CAM: {caminho_imagem}")
    
    try:
        # 1. Tentar ler a imagem (simulando o POST da catraca)
        with open(caminho_imagem, "rb") as f:
            imagem_bytes = f.read()
            
        # 2. A tua IA processa a foto (Valida brilho e extrai vetor)
        vetor = face_service.extract_face_vector(imagem_bytes)
        print("[IA] Rosto validado e vetor 128D extraído com sucesso!")
        
        # 3. O teu Motor de Busca procura no FAISS
        # Desempacotamos a tupla direto, pois sua função sempre retorna dois valores
        id_encontrado, distancia = faiss_service.search_vector(vetor)
        
        # 4. A Decisão (Agora validando o ID e não a tupla)
        if id_encontrado is not None:
            print(f"{VERDE}✅ ACESSO LIBERADO!{RESET}")
            print(f"Rosto reconhecido com ID: {id_encontrado} (Distância: {distancia:.4f})")
        else:
            print(f"{VERMELHO}❌ ACESSO NEGADO!{RESET}")
            print(f"Rosto desconhecido. Distância da IA: {distancia:.4f}")
            
    except ValueError as e:
        # Aqui entra o teu "Fail Gracioso" (ex: foto muito escura)
        print(f"{VERMELHO}⚠️ ERRO DE VALIDAÇÃO (Fail-Secure ativado):{RESET}")
        print(str(e))
    except FileNotFoundError:
        print(f"{VERMELHO}Erro: Imagem '{caminho_imagem}' não encontrada para o teste.{RESET}")

if __name__ == "__main__":
    print("Iniciando Motor de Biometria - ExpoTech 2026...")
    
    # Prepara o banco com a tua função seed
    # Certifica-te que o seed_ia.py gerou alguns dados antes de rodar isto
    import seed_ia 
    seed_ia.executar_seed()
    
    # Cenário A: O Caminho Feliz (Usa uma foto de alguém que já está no banco)
    # Substitui pelo caminho real de uma foto de teste
    demonstrar_cenario("CENÁRIO A - Aluno Cadastrado", "fotos_teste/foto_joao2.jpeg")
    
    # Cenário B: O Intruso (Usa uma foto de alguém que NÃO está no banco)
    demonstrar_cenario("CENÁRIO B - Tentativa de Invasão", "fotos_teste/foto_ryan.jpg")
    # Cenário C: Foto Escura / Sem Rosto (Para mostrar o bloqueio de hardware)
    demonstrar_cenario("CENÁRIO C - Foto no Escuro (Teste de Robustez)", "fotos_teste/foto_preta.png")