from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware.auth import require_enroll_key
from app.services import face_service, faiss_service
from app import models, schemas
from app.tasks.background import gravar_evento, upload_firebase
from fastapi import BackgroundTasks  
from app.config import get_settings  
from app.services.rbac_service import validar_regras_acesso  
from app.middleware.auth import require_device_key
import uuid  

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

# rota /verify

@router.post('/access/verify')
async def verify_access(
    response: Response,  # Adicionado para manipular os headers
    background_tasks: BackgroundTasks,
    dispositivo: models.Dispositivo = Depends(require_device_key),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)):
    
    settings = get_settings()
    
    # 1. Gerar o ID único da transação de acesso
    transaction_id = str(uuid.uuid4())
    
    # 2. Anexar ao Header da resposta (Custom Header: X-Transaction-ID)
    response.headers["X-Transaction-ID"] = transaction_id
    
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, detail={'erro':'Arquivo vazio.'})
    
    try: 
        vector = face_service.extract_face_vector(image_bytes)
    except face_service.LowQualityImageError:
        raise HTTPException(422, detail={'erro':'Qualidade insuficiente. Retry SVGA.'})
    except ValueError:
        raise HTTPException(400, detail={'erro':'Nenhuma face detectada.'})
        
    faiss_idx, dist = faiss_service.search_vector(vector, threshold=settings.faiss_distance_threshold)
    
    if faiss_idx is None:
        background_tasks.add_task(gravar_evento, db, None,
            dispositivo.id_dispositivo, 'BLOQUEADO', 'ROSTO_NAO_RECONHECIDO', dist)
        raise HTTPException(403, detail={'status':'bloqueado',
            'codigo_motivo':'ROSTO_NAO_RECONHECIDO','motivo':'Rosto não reconhecido.'})
    
    id_aluno = faiss_idx + 1
    permitido, motivo = validar_regras_acesso(id_aluno, dispositivo.id_dispositivo, db)
    aluno = db.query(models.Aluno).filter_by(id_aluno=id_aluno).first()
    
    if not permitido:
        background_tasks.add_task(gravar_evento, db, id_aluno,
            dispositivo.id_dispositivo, 'BLOQUEADO', motivo, dist)
        raise HTTPException(403, detail={'status':'bloqueado',
            'codigo_motivo':motivo, 'motivo':f'Acesso negado: {motivo}'})
    
    # Sucesso - As tasks de background rodam após o retorno do 200 OK
    background_tasks.add_task(gravar_evento, db, id_aluno,
        dispositivo.id_dispositivo, 'LIBERADO', '', dist)
    background_tasks.add_task(upload_firebase, image_bytes, aluno, dispositivo)
    
    return schemas.AcessoLiberado(
        status='liberado', 
        nome=aluno.nome_completo,
        matricula=aluno.matricula, 
        tipo_vinculo=aluno.tipo_vinculo
    )