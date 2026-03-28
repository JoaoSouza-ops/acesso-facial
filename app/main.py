# 1. CORREÇÃO AQUI: Adicionado o 'FastAPI' logo no começo do import
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from sqlalchemy.orm import Session
from app.database import get_db, engine
from app import models, schemas
from app.services import faiss_service, vision_service
import numpy as np

# ESTA LINHA É O "CONSTRUTOR" DO BANCO:
models.Base.metadata.create_all(bind=engine)

# 2. CORREÇÃO AQUI: Removida a linha duplicada e usado 'FastAPI' com letras maiúsculas
app = FastAPI(title="Sistema de Acesso Facial - ExpoTech")

@app.get("/teste-enroll", dependencies=[Depends(require_enroll_key)])
async def test_enroll():
    return {"status": "Sucesso", "permissao": "Enroll (Cadastro)"}

@app.get("/teste-admin", dependencies=[Depends(require_admin_key)])
async def test_admin():
    return {"status": "Sucesso", "permissao": "Admin"}

@app.get("/teste-dispositivo")
async def test_device(dispositivo = Depends(require_device_key)):
    # Aqui o require_device_key retorna o objeto do banco de dados
    return {
        "status": "Sucesso", 
        "dispositivo_id": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao
    }

@app.post("/api/v1/access/enroll", response_model=schemas.AlunoEnrollado, dependencies=[Depends(require_enroll_key)])
def enroll_student(
    # Transformamos o JSON em Multipart/Form-Data para suportar o upload da foto
    matricula: str = Form(...),
    nome_completo: str = Form(...),
    curso: str = Form(...),
    tipo_vinculo: str = Form(...),
    turno: str = Form(...),
    foto: UploadFile = File(...), # <-- O arquivo da foto entra aqui
    db: Session = Depends(get_db)
):
    print("--- TESTE: ROTA ACIONADA COM VISÃO COMPUTACIONAL ---")
    
    # =====================================================================
    # 1. TRADUÇÃO DA IMAGEM (Extraindo o vetor da foto)
    # =====================================================================
    try:
        foto_bytes = foto.file.read()
        vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes)
        vetor_para_faiss = np.array([vetor_128d], dtype=np.float32)
    except ValueError as e:
        # Barrado na porta: sem rosto ou com múltiplos rostos
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a imagem: {str(e)}")

    # =====================================================================
    # 2. SEGURANÇA E PERSISTÊNCIA
    # =====================================================================

    # IDEMPOTÊNCIA: Verifica se a matrícula já existe
    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == matricula).first()
    if aluno_existente:
        return schemas.AlunoEnrollado(
            id_aluno=aluno_existente.id_aluno,
            matricula=aluno_existente.matricula,
            mensagem="Idempotência: Aluno já estava cadastrado no sistema."
        )

    # UNICIDADE BIOMÉTRICA (Anti-Fraude): O rosto já pertence a outra pessoa?
    id_biometria_existente, _ = faiss_service.search_vector(vetor_para_faiss, threshold=0.4)
    if id_biometria_existente is not None:
        raise HTTPException(
            status_code=409, 
            detail="Conflito Biométrico: Este rosto já está cadastrado em outra matrícula."
        )

    # Salva no banco de dados
    novo_aluno = models.Aluno(
        matricula=matricula,
        nome_completo=nome_completo,
        curso=curso,
        tipo_vinculo=tipo_vinculo, 
        turno=turno
    )
    db.add(novo_aluno)
    db.commit()
    db.refresh(novo_aluno) 

    # Salva no FAISS (Persistência Atômica mantida!)
    try:
        faiss_service.add_vector(vetor_para_faiss, novo_aluno.id_aluno)
    except Exception as e:
        db.delete(novo_aluno)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Erro interno no motor biométrico: {str(e)}")

    return schemas.AlunoEnrollado(
        id_aluno=novo_aluno.id_aluno,
        matricula=novo_aluno.matricula,
        mensagem="Aluno cadastrado com sucesso!"
    )

@app.get("/teste-alunos", response_model=list[schemas.AlunoEnrollado])
def list_students(db: Session = Depends(get_db)):
    alunos = db.query(models.Aluno).all()
    return [
        schemas.AlunoEnrollado(
            id_aluno=a.id_aluno,
            matricula=a.matricula,
            mensagem="Cadastro Ativo"
        ) for a in alunos
    ]

@app.post("/teste_identificacao")
def teste_identificacao(request: schemas.IdentifyRequest, db: Session = Depends(get_db)):
    vetor_input = np.array(request.vetor_128d, dtype=np.float32)
    id_aluno, distancia_real = faiss_service.search_vector(vetor_input, threshold=2.0)

    if id_aluno is None and distancia_real == float('inf'):
        return {"erro": "Índice FAISS vazio. Cadastre alguém primeiro."}

    aluno = db.query(models.Aluno).filter(models.Aluno.id_aluno == id_aluno).first()
    nome = aluno.nome_completo if aluno else "Desconhecido"

    return {
        "resultado_bruto": {
            "distancia_l2": round(distancia_real, 4),
            "id_no_faiss": id_aluno,
            "nome_no_db": nome
        },
        "guia_de_decisao": {
            "eh_a_mesma_pessoa": distancia_real < 0.45,
            "duvida_razoavel": 0.45 <= distancia_real <= 0.6,
            "eh_outra_pessoa": distancia_real > 0.6
        }
    }