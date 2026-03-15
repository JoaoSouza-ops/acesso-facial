import face_recognition
import cv2
import numpy as np
import faiss
import json
import os

def extrair_biometria_segura(caminho_foto):
    """A mesma função blindada que usamos na API para garantir qualidade."""
    try:
        img_bgr = cv2.imread(caminho_foto)
        if img_bgr is None: return None
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        altura, largura = img_rgb.shape[:2]
        if largura > 800:
            proporcao = 800 / largura
            img_rgb = cv2.resize(img_rgb, (800, int(altura * proporcao)))

        encodings = face_recognition.face_encodings(img_rgb)
        return encodings[0] if len(encodings) > 0 else None
    except:
        return None

print("--- INICIANDO CADASTRO NO FAISS ---")

# 1. Definimos quem são os alunos e onde estão suas fotos de matrícula
alunos_para_cadastrar = [
    {"nome": "João", "foto": "fotos_teste/foto_joao1.jpg"},
    {"nome": "Ryan", "foto": "fotos_teste/foto_ryan.jpg"}
]

# 2. Configurando as estruturas do FAISS
dimensao_vetor = 128 # A IA do dlib sempre gera 128 números
indice_faiss = faiss.IndexFlatL2(dimensao_vetor) # L2 significa Distância Euclidiana
dicionario_nomes = {} # Para lembrar quem é o ID 0, ID 1, etc.
matriz_vetores = []

id_atual = 0

# 3. Processando cada aluno
for aluno in alunos_para_cadastrar:
    print(f"Processando foto de {aluno['nome']}...")
    vetor = extrair_biometria_segura(aluno['foto'])
    
    if vetor is not None:
        matriz_vetores.append(vetor)
        dicionario_nomes[id_atual] = aluno['nome']
        id_atual += 1
        print(f"✅ {aluno['nome']} cadastrado com sucesso! (ID: {id_atual-1})")
    else:
        print(f"❌ Falha ao cadastrar {aluno['nome']}. Rosto não detectado.")

# 4. Salvando tudo no banco de dados
if len(matriz_vetores) > 0:
    print("\nEmpacotando banco de dados...")
    # O FAISS exige que a matriz seja um array numpy do tipo float32
    vetores_np = np.array(matriz_vetores).astype('float32')
    
    # Adiciona todos os rostos ao FAISS de uma vez
    indice_faiss.add(vetores_np)
    
    # Salva o arquivo binário do FAISS no disco
    faiss.write_index(indice_faiss, "banco_biometrico.index")
    
    # Salva o dicionário de nomes para sabermos de quem é cada rosto
    with open("nomes_alunos.json", "w", encoding="utf-8") as f:
        json.dump(dicionario_nomes, f, ensure_ascii=False, indent=4)
        
    print("🚀 Banco de dados 'banco_biometrico.index' gerado com sucesso!")
    print(f"Total de alunos no banco: {indice_faiss.ntotal}")
else:
    print("Nenhum dado para salvar.")