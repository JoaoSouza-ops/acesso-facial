from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app import models
settings = get_settings()


def require_enroll_key(x_api_key_enroll: str = Header(alias='X-API-Key-Enroll')):
    if x_api_key_enroll != settings.api_key_enroll:
        raise HTTPException(status_code=401, detail={'erro':'Token inválido.'})


def require_admin_key(x_api_key_admin: str = Header(alias='X-API-Key-Admin')):
    if x_api_key_admin != settings.api_key_admin:
        raise HTTPException(status_code=401, detail={'erro':'Token inválido.'})


def require_device_key(
    x_api_key_device: str = Header(alias='X-API-Key-Device'),
    x_device_mac: str = Header(alias='X-Device-MAC'),
    db: Session = Depends(get_db)
) -> models.Dispositivo:
    """Valida chave E MAC Address. Retorna objeto Dispositivo. Mitiga spoofing."""
    disp = db.query(models.Dispositivo).filter(
        models.Dispositivo.api_key == x_api_key_device,
        models.Dispositivo.mac_address == x_device_mac,
        models.Dispositivo.ativo == 1
    ).first()
    if not disp:
        raise HTTPException(status_code=401, detail={
            'erro':'Credenciais inválidas ou MAC Address não reconhecido.'})
    return disp

