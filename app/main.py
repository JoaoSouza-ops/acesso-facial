from fastapi import FastAPI, Depends
from app.middleware.auth import require_enroll_key, require_admin_key, require_device_key

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