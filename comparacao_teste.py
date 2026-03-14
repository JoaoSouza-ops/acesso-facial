import face_recognition
import cv2

def extrair_biometria_segura(caminho_foto):
    print(f"Analisando: {caminho_foto}...")
    try:
        # 1. Carregamos com OpenCV para ignorar metadados que quebram a imagem
        img_bgr = cv2.imread(caminho_foto)
        if img_bgr is None:
            print(f"❌ Erro ao ler o arquivo {caminho_foto}.")
            return None

        # 2. Convertendo para as cores corretas (RGB)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # 3. Redimensionamento de segurança: se a foto for enorme, reduzimos para a IA não se perder
        altura, largura = img_rgb.shape[:2]
        if largura > 800:
            proporcao = 800 / largura
            nova_altura = int(altura * proporcao)
            img_rgb = cv2.resize(img_rgb, (800, nova_altura))

        # 4. Buscando o rosto na imagem limpa
        encodings = face_recognition.face_encodings(img_rgb)
        
        if len(encodings) > 0:
            print(f"✅ Rosto validado com sucesso!")
            return encodings[0]
        else:
            print(f"❌ ALERTA: Nenhum rosto encontrado. Verifique iluminação ou acessórios.")
            return None

    except Exception as e:
        print(f"❌ Erro na extração: {e}")
        return None

print("--- INICIANDO DIAGNÓSTICO DA CATRACA ---")

encoding_joao_cadastro = extrair_biometria_segura("fotos_teste/foto_joao1.jpg")
encoding_joao_catraca  = extrair_biometria_segura("fotos_teste/foto_joao2.jpg")
encoding_ryan_catraca  = extrair_biometria_segura("fotos_teste/foto_ryan.jpg")

if encoding_joao_cadastro is not None and encoding_joao_catraca is not None and encoding_ryan_catraca is not None:
    print("\n--- TESTE DE ACESSO ---")
    
    resultado_joao = face_recognition.compare_faces([encoding_joao_cadastro], encoding_joao_catraca)[0]
    print(f"João 1 e João 2 são a mesma pessoa? {'Sim (Acesso Liberado)' if resultado_joao else 'Não (Bloqueado)'}")
    
    resultado_ryan = face_recognition.compare_faces([encoding_joao_cadastro], encoding_ryan_catraca)[0]
    print(f"João 1 e Ryan são a mesma pessoa? {'Sim (Acesso Liberado)' if resultado_ryan else 'Não (Bloqueado)'}")
else:
    print("\n⛔ O teste de acesso foi cancelado porque uma ou mais fotos falharam na leitura.")