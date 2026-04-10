from fastapi import FastAPI, UploadFile, File, Form
import face_recognition
import cv2
import numpy as np
import faiss
import json

app = FastAPI(title="API Catraca Facial - Enterprise (FAISS)")

print("Carregando o banco de dados FAISS...")
try:
    # 1. Carrega o banco vetorial e o mapa de nomes
    indice_faiss = faiss.read_index("banco_biometrico.index")
    with open("nomes_alunos.json", "r", encoding="utf-8") as f:
        dicionario_nomes = json.load(f)
    print(f"✅ Banco carregado com sucesso! Total de alunos: {indice_faiss.ntotal}")
except Exception as e:
    indice_faiss = None
    print(f"❌ Erro ao carregar o banco de dados: {e}")

@app.post("/verificar-acesso")
async def verificar_acesso(arquivo: UploadFile = File(...)):

    print(f"\n[CATRACA] Foto recebida: {arquivo.filename}")
    
    if indice_faiss is None:
        return {"sucesso": False, "mensagem": "Erro interno: Banco de dados inativo."}

    try:
        # Tratamento de imagem blindado (OpenCV)
        conteudo = await arquivo.read()
        nparr = np.frombuffer(conteudo, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            return {"sucesso": False, "mensagem": "Arquivo inválido."}

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        altura, largura = img_rgb.shape[:2]
        if largura > 800:
            img_rgb = cv2.resize(img_rgb, (800, int(altura * (800 / largura))))

        encodings = face_recognition.face_encodings(img_rgb)
        
        if len(encodings) == 0:
            return {"sucesso": False, "acesso": False, "mensagem": "Nenhum rosto detectado."}

        # --- A MÁGICA DO FAISS COMEÇA AQUI ---
        encoding_catraca = encodings[0]
        
        # FAISS exige que a pergunta seja feita em formato de matriz 2D float32
        vetor_busca = np.array([encoding_catraca], dtype=np.float32)
        
        # Busca o 1 rosto mais parecido (k=1) no banco de dados inteiro
        k = 1
        distancias, indices = indice_faiss.search(vetor_busca, k)
        
        # FAISS retorna a distância ao quadrado. Tiramos a raiz para manter nossa nota de 0 a 1.
        distancia_real = float(np.sqrt(distancias[0][0]))
        id_encontrado = str(indices[0][0]) # O JSON salva os IDs como texto
        
        print(f"[FAISS] ID mais próximo: {id_encontrado} | Distância: {distancia_real:.2f}")

        # O nosso Limiar de Tolerância (Threshold) rigoroso
        if distancia_real <= 0.50:
            nome_aluno = dicionario_nomes.get(id_encontrado, "Desconhecido")
            print(f"[CATRACA] Veredito: LIBERADO ✅ Bem-vindo(a), {nome_aluno}!")
            return {"sucesso": True, "acesso": True, "aluno": nome_aluno, "mensagem": f"Acesso Liberado para {nome_aluno}!"}
        else:
            print("[CATRACA] Veredito: BLOQUEADO ⛔ Intruso.")
            return {"sucesso": True, "acesso": False, "aluno": "Desconhecido", "mensagem": "Acesso Bloqueado!"}

    except Exception as e:
        return {"sucesso": False, "mensagem": f"Erro ao processar: {e}"}
    
@app.post("/cadastrar")
async def cadastrar_aluno(nome: str = Form(...), arquivo: UploadFile = File(...)):
    global indice_faiss, dicionario_nomes
    
    print(f"\n[SECRETARIA] Iniciando cadastro para: {nome}")
    
    if indice_faiss is None:
        return {"sucesso": False, "mensagem": "Erro: Banco de dados offline."}

    try:
        # 1. Tratamento da foto recebida
        conteudo = await arquivo.read()
        nparr = np.frombuffer(conteudo, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            return {"sucesso": False, "mensagem": "Arquivo de imagem inválido."}

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        # 2. Extração da Biometria
        encodings = face_recognition.face_encodings(img_rgb)
        if len(encodings) == 0:
            return {"sucesso": False, "mensagem": "Nenhum rosto detectado na foto. Tente novamente."}
            
        novo_vetor = encodings[0]
        
        # 3. Inserindo no FAISS dinamicamente
        vetor_np = np.array([novo_vetor], dtype=np.float32)
        indice_faiss.add(vetor_np)
        
        # 4. Atualizando nosso mapa de nomes
        # O ID do novo aluno será o número total de alunos - 1
        novo_id = indice_faiss.ntotal - 1 
        dicionario_nomes[str(novo_id)] = nome
        
        # 5. Salvando as alterações no disco (Para não perder se reiniciar o PC)
        faiss.write_index(indice_faiss, "banco_biometrico.index")
        with open("nomes_alunos.json", "w", encoding="utf-8") as f:
            json.dump(dicionario_nomes, f, ensure_ascii=False, indent=4)
            
        print(f"[SECRETARIA] ✅ {nome} cadastrado com sucesso com ID {novo_id}!")
        return {"sucesso": True, "mensagem": f"Aluno(a) {nome} cadastrado(a) com sucesso!"}

    except Exception as e:
        return {"sucesso": False, "mensagem": f"Erro no cadastro: {e}"}