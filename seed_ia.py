import os
import json
import faiss
from app.services.face_service import extract_face_vector
from app.services import faiss_service

def executar_seed():
    print("🌱 Iniciando Seed do Módulo de IA...")
    
    # Configurações básicas
    pasta_fotos = "tests/fixtures"
    ficheiro_index = "banco_biometrico.index"
    mapa_nomes = "mapa_alunos.json"
    
    # Lista de fotos para cadastrar inicialmente
    # Formato: (Nome do Aluno, Nome do Arquivo)
    alunos_iniciais = [
        ("João Aluno", "foto_joao1.jpg"),
    # Adicione outros se tiver mais fotos em fixtures
    ]
    
    vetores = []
    dicionario_mapa = {}
    
    for i, (nome, ficheiro) in enumerate(alunos_iniciais):
        caminho = os.path.join(pasta_fotos, ficheiro)
        
        if not os.path.exists(caminho):
            print(f"⚠️ Aviso: Foto {ficheiro} não encontrada em {pasta_fotos}. Pulando...")
            continue
            
        try:
            print(f"📸 Processando: {nome}...")
            with open(caminho, "rb") as f:
                img_bytes = f.read()
            
            vetor = extract_face_vector(img_bytes)
            vetores.append(vetor)
            
            # O ID no FAISS é sequencial (0, 1, 2...)
            dicionario_mapa[str(i)] = {
                "nome": nome,
                "foto_origem": ficheiro
            }
        except Exception as e:
            print(f"❌ Erro ao processar {nome}: {e}")

    if vetores:
        # Inicializa o FAISS com os vetores encontrados
        faiss_service.initialize_index(vetores, list(dicionario_mapa.keys()))
        
        # Grava o ficheiro .index no disco para o Ian carregar
        faiss.write_index(faiss_service._index, ficheiro_index)
        
        # Grava o JSON de referência
        with open(mapa_nomes, "w", encoding="utf-8") as f:
            json.dump(dicionario_mapa, f, indent=4, ensure_ascii=False)
            
        print(f"\n✅ Seed concluído! {len(vetores)} alunos cadastrados.")
        print(f"📁 Ficheiros gerados: {ficheiro_index} e {mapa_nomes}")
    else:
        print("❌ Falha: Nenhum vetor foi gerado. Verifique as fotos em fixtures.")

if __name__ == "__main__":
    executar_seed()