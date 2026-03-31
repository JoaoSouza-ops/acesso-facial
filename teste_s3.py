import os
from app.services import s3_service

def testar_conexao_s3():
    print("🚀 A iniciar teste de ligação com a AWS S3...")
    
    ficheiro_teste = "vector_index.index"
    
    # Se ainda não existir um índice real na sua pasta, criamos um ficheiro falso só para o teste
    ficheiro_criado_agora = False
    if not os.path.exists(ficheiro_teste):
        print("A criar um ficheiro de teste temporário...")
        with open(ficheiro_teste, "w") as f:
            f.write("dados biometricos confidenciais da unifecaf")
        ficheiro_criado_agora = True

    # --- TESTE 1: UPLOAD (Guardar na Nuvem) ---
    print("\n--- TESTE 1: UPLOAD ---")
    sucesso_upload = s3_service.carregar_indice_para_nuvem()
    
    if sucesso_upload:
        print("✅ Upload concluído. O cofre da AWS recebeu o ficheiro!")
    else:
        print("❌ Falha no Upload. Verifique as credenciais no .env e o nome exato do bucket.")
        return  # Interrompe o teste se o upload falhar

    # --- TESTE 2: DOWNLOAD (Simular o reinício do servidor) ---
    print("\n--- TESTE 2: DOWNLOAD ---")
    
    # Apagamos o ficheiro local para provar que a AWS o consegue devolver
    os.remove(ficheiro_teste)
    print("Ficheiro local apagado para simular a 'amnésia' do servidor...")
    
    sucesso_download = s3_service.descarregar_indice_da_nuvem()
    
    if sucesso_download and os.path.exists(ficheiro_teste):
        print("✅ Download concluído. A memória do FAISS foi restaurada da nuvem com sucesso!")
    else:
        print("❌ Falha no Download.")

    # Limpeza do ficheiro falso (se o criámos apenas para este teste)
    if ficheiro_criado_agora and os.path.exists(ficheiro_teste):
        os.remove(ficheiro_teste)

if __name__ == "__main__":
    testar_conexao_s3()