from fastapi import FastAPI, Depends
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.services import faiss_service
import numpy as np


app = FastAPI(title="Sistema Acesso Facial - Teste Auth")

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
def enroll_student(request: schemas.EnrollRequest, db: Session = Depends(get_db)):
    print("--- TESTE: ROTA ACIONADA ---")
    # 1. Verifica se a matrícula já existe
    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == request.matricula).first()
    if aluno_existente:
        raise HTTPException(status_code=400, detail="Matrícula já cadastrada no sistema.")

    # 2. Salva no banco de dados
    novo_aluno = models.Aluno(
        matricula=request.matricula,
        nome_completo=request.nome_completo,
        curso=request.curso,
        tipo_vinculo=request.tipo_vinculo.value,
        turno=request.turno.value
    )
    db.add(novo_aluno)
    db.commit()
    db.refresh(novo_aluno) 

    # 3. Prepara o vetor para o seu FAISS
    # Aqui usamos 'vetor_para_faiss' para não ter erro de nome
    vetor_para_faiss = np.array([request.vetor_128d], dtype=np.float32)
    
    try:
        # Chamada limpa para o seu serviço
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