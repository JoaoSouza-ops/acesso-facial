# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    api_key_device: str
    api_key_enroll: str
    api_key_admin: str
    DATABASE_URL: str
    THRESHOLD_DUPLICATA: float = 0.45   # usado no enroll (detectar sósias)
    THRESHOLD_ACESSO: float = 0.60      # usado no verify (reconhecer na catraca)
    firebase_credentials_path: str = ''
    model_config = model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
@lru_cache()
def get_settings(): return Settings()