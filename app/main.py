from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key
from app.database import get_db, engine
from app import models, schemas
from app.services import vision_service

# O "CONSTRUTOR" DO BANCO
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema de Acesso Facial - ExpoTech")

@app.get("/teste-enroll", dependencies=[Depends(require_enroll_key)])
async def test_enroll():
    return {"status": "Sucesso", "permissao": "Enroll (Cadastro)"}

@app.get("/teste-admin", dependencies=[Depends(require_admin_key)])
async def test_admin():
    return {"status": "Sucesso", "permissao": "Admin"}

@app.get("/teste-dispositivo")
async def test_device(dispositivo = Depends(require_device_key)):
    return {
        "status": "Sucesso", 
        "dispositivo_id": dispositivo.id_dispositivo,
        "localizacao": dispositivo.localizacao
    }

# Mudamos o response_model para o novo Schema (AlunoResponse)
@app.post("/api/v1/access/enroll", response_model=schemas.AlunoResponse, dependencies=[Depends(require_enroll_key)])
def enroll_student(
    # Agora o FastAPI força os Enums da DBA. Se vier errado, dá Erro 422 automático!
    matricula: str = Form(...),
    nome_completo: str = Form(...),
    curso: str = Form(...),
    tipo_vinculo: schemas.TipoVinculoEnum = Form(...),
    turno: schemas.TurnoEnum = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    print("--- INICIANDO CADASTRO COM PGVECTOR ---")
    
    # =====================================================================
    # 1. TRADUÇÃO DA IMAGEM
    # =====================================================================
    try:
        foto_bytes = foto.file.read()
        # O pgvector aceita listas nativas do Python, adeus numpy!
        vetor_128d = vision_service.extrair_vetor_da_imagem(foto_bytes) 
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a imagem: {str(e)}")

    # =====================================================================
    # 2. SEGURANÇA E PERSISTÊNCIA
    # =====================================================================

    # IDEMPOTÊNCIA
    aluno_existente = db.query(models.Aluno).filter(models.Aluno.matricula == matricula).first()
    if aluno_existente:
        # Se já existe, devolvemos o objeto para não quebrar o frontend
        return aluno_existente

    # UNICIDADE BIOMÉTRICA (A Mágica do pgvector)
    # Busca no banco alguém com o rosto matematicamente parecido (distância L2 < 0.45)
    sosia = db.query(models.Aluno).filter(
        models.Aluno.vetor_128d.l2_distance(vetor_128d) < 0.45
    ).first()

    if sosia:
        raise HTTPException(
            status_code=409, 
            detail=f"Conflito Biométrico: Rosto muito similar ao do(a) aluno(a) {sosia.nome_completo}."
        )

    # SALVA TUDO DE UMA VEZ SÓ (ACID)
    novo_aluno = models.Aluno(
        matricula=matricula,
        nome_completo=nome_completo,
        curso=curso,
        tipo_vinculo=tipo_vinculo, 
        turno=turno,
        vetor_128d=vetor_128d # <-- A biometria é injetada direto na coluna!
    )
    
    db.add(novo_aluno)
    db.commit()
    db.refresh(novo_aluno) 

    return novo_aluno


@app.get("/teste-alunos", response_model=list[schemas.AlunoResponse])
def list_students(db: Session = Depends(get_db)):
    return db.query(models.Aluno).all()


@app.post("/teste_identificacao")
def teste_identificacao(request: dict, db: Session = Depends(get_db)):
    # Rota temporária adaptada para pgvector. Recebe um JSON com "vetor_128d"
    vetor_input = request.get("vetor_128d")
    
    if not vetor_input:
        raise HTTPException(status_code=400, detail="Vetor não fornecido")

    # Calcula a distância de TODOS os alunos e traz o menor valor
    # O pgvector lida com a matemática brutal no PostgreSQL
    aluno_mais_proximo = db.query(
        models.Aluno,
        models.Aluno.vetor_128d.l2_distance(vetor_input).label("distancia")
    ).order_by("distancia").first()

    if not aluno_mais_proximo:
        return {"erro": "Banco de dados vazio. Cadastre alguém primeiro."}

    aluno, distancia_real = aluno_mais_proximo

    return {
        "resultado_bruto": {
            "distancia_l2": round(distancia_real, 4),
            "id_no_db": aluno.id_aluno,
            "nome_no_db": aluno.nome_completo
        },
        "guia_de_decisao": {
            "eh_a_mesma_pessoa": distancia_real < 0.45,
            "duvida_razoavel": 0.45 <= distancia_real <= 0.6,
            "eh_outra_pessoa": distancia_real > 0.6
        }
    }