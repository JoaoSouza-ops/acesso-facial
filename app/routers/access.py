from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware.auth import require_enroll_key
from app.services import face_service, faiss_service
from app import models, schemas


router = APIRouter(prefix='/api/v1', tags=['Acesso Biométrico'])


@router.post('/access/enroll', status_code=201, dependencies=[Depends(require_enroll_key)])
async def enroll_student(
    nome_completo: str=Form(...), matricula: str=Form(...),
    curso: str=Form(...), tipo_vinculo: str=Form(...), turno: str=Form(...),
    file: UploadFile=File(...), db: Session=Depends(get_db)):
    if db.query(models.Aluno).filter_by(matricula=matricula).first():
        raise HTTPException(409, detail={'erro':'Matrícula já cadastrada.',
            'campo':'matricula','valor_conflitante':matricula})
    image_bytes = await file.read()
    try: vector = face_service.extract_face_vector(image_bytes)
    except (face_service.LowQualityImageError, ValueError) as e:
        raise HTTPException(422, detail={'erro': str(e)})
    aluno = models.Aluno(matricula=matricula, nome_completo=nome_completo,
        curso=curso, tipo_vinculo=tipo_vinculo, turno=turno,
        vetor_128d=face_service.vector_to_blob(vector))
    db.add(aluno); db.commit(); db.refresh(aluno)
    faiss_service.add_vector(vector)
    return schemas.AlunoEnrollado(id_aluno=aluno.id_aluno, matricula=aluno.matricula,
        nome_completo=aluno.nome_completo, mensagem='Cadastro realizado com sucesso.')