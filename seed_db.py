from app.database import engine, SessionLocal
from app import models
models.Base.metadata.create_all(bind=engine)
db = SessionLocal()
for tipo, bloco in [
    ('GRADUACAO','SEDE'),('GRADUACAO','BLOCO_AULAS'),
    ('POS_GRADUACAO','SEDE'),('POS_GRADUACAO','BLOCO_AULAS'),
    ('PROFESSOR','SEDE'),('PROFESSOR','BLOCO_AULAS'),
    ('FUNCIONARIO','SEDE'),   # sem BLOCO_AULAS por padrão
]:
    db.add(models.RegrasBlocoVinculo(tipo_vinculo=tipo, bloco=bloco))
db.add(models.Dispositivo(
    api_key='hub-dev-device-chave-secreta-123',
    mac_address='00:11:22:33:44:55',
    localizacao='Entrada Principal — Sede',
    bloco='SEDE', ativo=1
))
db.commit(); db.close(); print('Seed concluído.')