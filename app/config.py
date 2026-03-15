# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
class Settings(BaseSettings):
    api_key_device: str
    api_key_enroll: str
    api_key_admin: str
    database_url: str = 'sqlite:///./acesso_facial.db'
    faiss_distance_threshold: float = 0.6
    firebase_credentials_path: str = ''
    class Config:
        env_file = '.env'
        case_sensitive = False
@lru_cache()
def get_settings(): return Settings()