import face_recognition as fr
import numpy as np
import cv2
import os

def processar_rosto_final(caminho_input):
    print(f"Limpando imagem: {caminho_input}")
    
    try:
        # 1. Carrega a imagem do jeito mais bruto possível
        img = cv2.imread(caminho_input)
        if img is None:
            print("Erro ao ler arquivo.")
            return

        # 2. Redimensiona para ser leve
        img = cv2.resize(img, (600, 800))

        # 3. SALVA uma versão temporária em BMP (BMP não tem compressão nem metadados chatos)
        caminho_temp = "temp_limpa.bmp"
        cv2.imwrite(caminho_temp, img)

        # 4. Agora pedimos para a biblioteca de IA ler esse arquivo direto do disco
        # O load_image_file do face_recognition é quem vai gerenciar a memória agora
        img_para_ia = fr.load_image_file(caminho_temp)

        print(f"DEBUG: Tipo da imagem carregada: {img_para_ia.dtype}")
        print("Buscando rosto...")

        encodings = fr.face_encodings(img_para_ia)

        if len(encodings) > 0:
            print("\n✅ FINALMENTE! Rosto encontrado!")
            np.save("meu_rosto.npy", encodings[0])
            print("Vetor salvo com sucesso.")
        else:
            print("\n❌ A IA leu a imagem, mas não achou um rosto. Tente uma foto com mais luz.")

        # Limpa o rastro
        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)

    except Exception as e:
        print(f"\n❌ Erro persistente: {e}")

processar_rosto_final("fotos_teste/foto_joao2.jpg")