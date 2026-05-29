from app.database import SessionLocal
from app import models

db = SessionLocal()

# overrides são deletados em cascade automaticamente
db.query(models.OverrideAcesso).delete()
db.query(models.Aluno).delete()
db.commit()
db.close()

print("Alunos e overrides removidos. Eventos mantidos com id_aluno = NULL.")