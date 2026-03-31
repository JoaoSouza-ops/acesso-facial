# app/services/s3_service.py
import boto3
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do ficheiro .env para a memória
load_dotenv()

AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "smartbuilds-biometria-faiss")
NOME_FICHEIRO_LOCAL = "vector_index.index"
NOME_FICHEIRO_S3 = "vector_index.index"

# Inicializa o cliente S3 (O boto3 lê o .env automaticamente)
s3_client = boto3.client('s3')


def descarregar_indice_da_nuvem():
    """Tenta descarregar o índice FAISS do S3 quando a aplicação arranca."""
    try:
        print(f"☁️ A tentar descarregar o {NOME_FICHEIRO_S3} do S3...")
        s3_client.download_file(AWS_BUCKET_NAME, NOME_FICHEIRO_S3, NOME_FICHEIRO_LOCAL)
        print("✅ Índice biométrico descarregado com sucesso da nuvem!")
        return True
    except Exception as e:
        print(f"⚠️ Ficheiro não encontrado no S3 ou erro de ligação. Um índice vazio será utilizado. Detalhe: {e}")
        return False

def carregar_indice_para_nuvem():
    """Carrega o ficheiro local atualizado para o S3."""
    try:
        print(f"☁️ A guardar o {NOME_FICHEIRO_LOCAL} atualizado no S3...")
        s3_client.upload_file(NOME_FICHEIRO_LOCAL, AWS_BUCKET_NAME, NOME_FICHEIRO_S3)
        print("✅ Novo índice biométrico guardado com sucesso na nuvem!")
        return True
    except Exception as e:
        print(f"❌ Erro ao guardar o índice no S3: {e}")
        return False