import requests
import face_recognition # Ou a biblioteca que você está usando para gerar o vetor
import numpy as np
import json

# --- CONFIGURAÇÕES ---
API_URL = "http://127.0.0.1:8000/api/v1/access/enroll"
API_KEY = "chave_secreta_enroll_123" # A chave que definimos no .env
FOTO_PATH = "fotos_teste/tom_holland.jpg" # Ajuste para uma foto sua

# Dados do Aluno
MATRICULA = "20260005"
NOME = "Lorde Ella Teste"

def gerar_vetor_real(caminho_foto):
    print(f"📸 Carregando foto: {caminho_foto}...")
    image = face_recognition.load_image_file(caminho_foto)
    
    # Encontra os rostos na imagem
    face_encodings = face_recognition.face_encodings(image)
    
    if len(face_encodings) == 0:
        print("❌ Erro: Nenhum rosto encontrado na foto.")
        return None
    
    # Pega o vetor do primeiro rosto encontrado
    print("✅ Vetor facial gerado com sucesso!")
    return face_encodings[0].tolist() # Converte numpy array para lista Python

def enviar_enroll(vetor_real):
    headers = {
        "X-API-Key-Enroll": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "matricula": MATRICULA,
        "nome_completo": NOME,
        "curso": "Engenharia de IA",
        "tipo_vinculo": "Regular",
        "turno": "Noturno",
        "vetor_128d": vetor_real # O vetor real gerado pela foto
    }
    
    print(f"🚀 Enviando requisição de Enroll para a API...")
    response = requests.post(API_URL, headers=headers, json=payload)
    
    if response.status_code == 200:
        print("🎉 SUCESSO! Aluno cadastrado com foto real.")
        print("Resposta:", response.json())
    else:
        print(f"❌ FALHA (Status {response.status_code})")
        print("Erro:", response.text)

# --- EXECUÇÃO ---
if __name__ == "__main__":
    vetor = gerar_vetor_real(FOTO_PATH)
    if vetor:
        enviar_enroll(vetor)