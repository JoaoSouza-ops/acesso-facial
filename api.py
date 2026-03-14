from fastapi import FastAPI, UploadFile, File
import face_recognition
import cv2
import numpy as np

app = FastAPI(title="API Catraca Facial - MVP")

print("Carregando o banco de dados...")
try:
    # Carregamos o seu DNA digital salvo anteriormente
    encoding_joao_cadastro = np.load("meu_rosto.npy")
    print("✅ Banco de dados carregado com sucesso (João)")
except Exception as e:
    encoding_joao_cadastro = None
    print(f"❌ Erro ao carregar meu_rosto.npy: {e}")

@app.post("/verificar-acesso")
async def verificar_acesso(arquivo: UploadFile = File(...)):
    # --- NOVO: Raio-X do que está chegando ---
    print(f"\n[CATRACA] Arquivo recebido da internet: {arquivo.filename}")
    
    if encoding_joao_cadastro is None:
        return {"sucesso": False, "mensagem": "Erro interno: Banco de dados não carregado."}

    try:
        conteudo = await arquivo.read()
        nparr = np.frombuffer(conteudo, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            return {"sucesso": False, "mensagem": "Arquivo de imagem inválido."}

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        altura, largura = img_rgb.shape[:2]
        if largura > 800:
            proporcao = 800 / largura
            nova_altura = int(altura * proporcao)
            img_rgb = cv2.resize(img_rgb, (800, nova_altura))

        encodings = face_recognition.face_encodings(img_rgb)
        
        if len(encodings) == 0:
            return {"sucesso": False, "acesso": False, "mensagem": "Nenhum rosto detectado na foto."}

        encoding_catraca = encodings[0]

        # --- NOVO: Ver a distância matemática real ---
        resultado = face_recognition.compare_faces([encoding_joao_cadastro], encoding_catraca)[0]
        # --- A Regra de Negócio Ajustada (O Juiz Rigoroso) ---
        distancia = face_recognition.face_distance([encoding_joao_cadastro], encoding_catraca)[0]
        
        # Apertamos a segurança! Só entra se a diferença for 0.50 ou menor
        limite_de_seguranca = 0.50 
        resultado = bool(distancia <= limite_de_seguranca)

        print(f"[CATRACA] Distância matemática calculada: {distancia:.2f}")

        if resultado:
            print("[CATRACA] Veredito: LIBERADO ✅")
            return {"sucesso": True, "acesso": True, "aluno": "João", "mensagem": "Acesso Liberado!"}
        else:
            print("[CATRACA] Veredito: BLOQUEADO ⛔")
            return {"sucesso": True, "acesso": False, "aluno": "Desconhecido", "mensagem": "Acesso Bloqueado!"}


    except Exception as e:
        return {"sucesso": False, "mensagem": f"Erro ao processar: {e}"}