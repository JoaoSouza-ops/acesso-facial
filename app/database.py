from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings # Importa a função em vez da variável

# Executa a função para carregar as variáveis do .env
settings = get_settings()

# O SQLAlchemy vai usar o DATABASE_URL que configurámos
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Criação do motor de ligação (PostgreSQL)
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()