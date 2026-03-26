from fastapi import FastAPI, Depends
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.services import faiss_service
import numpy as np

from app.database import engine # Importa a conexão do banco
from app import models         # Importa os modelos (tabela Aluno)

# ESTA LINHA É O "CONSTRUTOR" DO BANCO:
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema de Acesso Facial")

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
    
    # Prepara o vetor logo no início, pois vamos usá-lo para a verificação anti-fraude
    vetor_para_faiss = np.array([request.vetor_128d], dtype=np.float32)

    # 1. IDEMPOTÊNCIA: Verifica se a matrícula já existe
    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == request.matricula).first()
    if aluno_existente:
        # Em vez de dar erro 400 (que quebra o app), retornamos sucesso informando que já estava cadastrado.
        # Se o app enviar 3 vezes sem querer, a resposta será a mesma, sem duplicar dados.
        return schemas.AlunoEnrollado(
            id_aluno=aluno_existente.id_aluno,
            matricula=aluno_existente.matricula,
            mensagem="Idempotência: Aluno já estava cadastrado no sistema."
        )

    # 2. UNICIDADE BIOMÉTRICA (Anti-Fraude): O rosto já pertence a outra pessoa?
    # Usamos o threshold mais rígido (ex: 0.4) para ter certeza que não é um "sósia" ou fraude.
    id_biometria_existente, _ = faiss_service.search_vector(vetor_para_faiss, threshold=0.4)
    if id_biometria_existente is not None:
        raise HTTPException(
            status_code=409, # 409 = Conflict
            detail="Conflito Biométrico: Este rosto já está cadastrado em outra matrícula."
        )

    # 3. Salva no banco de dados
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

    # 4. Salva no FAISS (Persistência Atômica mantida!)
    try:
        # Chamada limpa para o seu serviço
        faiss_service.add_vector(vetor_para_faiss, novo_aluno.id_aluno)
    except Exception as e:
        # Ocorreu um erro na IA? O banco faz o rollback automático deletando o aluno.
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
    # Busca todos os alunos na tabela do SQLite
    alunos = db.query(models.Aluno).all()
    
    # Retorna a lista formatada conforme o schema do Ian
    return [
        schemas.AlunoEnrollado(
            id_aluno=a.id_aluno,
            matricula=a.matricula,
            mensagem="Cadastro Ativo"
        ) for a in alunos
    ]

@app.post("/teste_identificacao")
def teste_identificacao(request: schemas.IdentifyRequest, db: Session = Depends(get_db)):
    # 1. Prepara o vetor (garantindo que seja um array numpy)
    vetor_input = np.array(request.vetor_128d, dtype=np.float32)

    # 2. Chama a sua função original
    # Usamos um threshold bem alto (ex: 2.0) apenas para este teste 
    # para que ele nunca retorne None enquanto estamos calibrando
    id_aluno, distancia_real = faiss_service.search_vector(vetor_input, threshold=2.0)

    if id_aluno is None and distancia_real == float('inf'):
        return {"erro": "Índice FAISS vazio. Cadastre alguém primeiro."}

    # 3. Busca o nome do aluno no banco de dados
    # Note que aqui usamos o 'id_aluno' que o FAISS encontrou como vizinho mais próximo
    aluno = db.query(models.Aluno).filter(models.Aluno.id_aluno == id_aluno).first()
    nome = aluno.nome_completo if aluno else "Desconhecido"

    # 4. Resposta de Calibração
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