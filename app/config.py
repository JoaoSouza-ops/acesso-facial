# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
class Settings(BaseSettings):
    api_key_device: str
    api_key_enroll: str
    api_key_admin: str
    DATABASE_URL: str
    THRESHOLD_DUPLICATA: float = 0.45   # usado no enroll (detectar sósias)
    THRESHOLD_ACESSO: float = 0.60      # usado no verify (reconhecer na catraca)
    firebase_credentials_path: str = ''
    class Config:
        env_file = '.env'
        case_sensitive = False
@lru_cache()
def get_settings(): return Settings()