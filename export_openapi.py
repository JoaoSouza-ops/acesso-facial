import yaml
from app.main import app

# Extrai o esquema gerado automaticamente pelo FastAPI
openapi_schema = app.openapi()
# Força a versão exigida pela documentação
openapi_schema["openapi"] = "3.1.0" 

# Salva no formato YAML
with open("openapi.yaml", "w", encoding="utf-8") as f:
    yaml.dump(openapi_schema, f, sort_keys=False, allow_unicode=True)
    
print("Contrato openapi.yaml exportado com sucesso!")