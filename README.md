# 🎓 Sistema de Acesso Facial — ExpoTech

> **API de controle de acesso biométrico por reconhecimento facial**, desenvolvida para automação de catracas universitárias com suporte a ESP32-CAM, dashboard em tempo real e regras de permissão baseadas em papel (RBAC).

---

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e Configuração](#instalação-e-configuração)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Como Funciona](#como-funciona)
- [Endpoints da API](#endpoints-da-api)
- [Sistema RBAC](#sistema-rbac)
- [WebSocket — Feed em Tempo Real](#websocket--feed-em-tempo-real)
- [Testes](#testes)
- [Estrutura do Projeto](#estrutura-do-projeto)

---

## Visão Geral

O **Sistema de Acesso Facial** é uma API REST construída com **FastAPI** que realiza reconhecimento facial em tempo real para liberação ou bloqueio de catracas em ambiente universitário. O fluxo completo é:

1. Uma câmera (ESP32-CAM ou equivalente) captura uma foto na catraca.
2. A foto é enviada para a API via HTTP.
3. A IA extrai um **vetor biométrico de 128 dimensões** do rosto detectado.
4. O vetor é comparado com o banco biométrico via busca de similaridade L2 com **pgvector** (PostgreSQL).
5. O sistema aplica as regras de **RBAC** para decidir se o acesso é liberado ou bloqueado.
6. O resultado é transmitido em tempo real para um painel de segurança via **WebSocket**.

---

## Arquitetura

```
ESP32-CAM / Cliente HTTP
        │  POST /api/v1/access/verify  (imagem)
        ▼
┌─────────────────────────────────────────────────────┐
│                   FastAPI (app/main.py)              │
│                                                     │
│  ┌──────────────┐   ┌──────────────┐  ┌──────────┐ │
│  │ vision_service│   │ rbac_service │  │ middleware│ │
│  │  (face_service│   │  4 regras em │  │   auth   │ │
│  │   + PIL/dlib) │   │  sequência   │  │ (API Key │ │
│  └──────┬───────┘   └──────┬───────┘  │ + MAC)   │ │
│         │                  │          └──────────┘ │
└─────────┼──────────────────┼─────────────────────┘
          │ vetor 128D        │ id_aluno, id_dispositivo
          ▼                  ▼
   ┌──────────────────────────────┐
   │   PostgreSQL + pgvector      │
   │  (busca L2 nos vetores)      │
   └──────────────────────────────┘
          │
          ▼
   WebSocket broadcast → Dashboard de Segurança
```

---

## Tecnologias Utilizadas

| Camada           | Tecnologia                                   |
|------------------|----------------------------------------------|
| Framework Web    | FastAPI + Uvicorn                            |
| Banco de Dados   | PostgreSQL com extensão **pgvector**         |
| ORM              | SQLAlchemy                                   |
| IA / Biometria   | `face_recognition` (dlib) + OpenCV + Pillow  |
| Busca Vetorial   | pgvector (distância L2 nativa no PostgreSQL) |
| Validação        | Pydantic v2                                  |
| Tempo Real       | WebSocket nativo do FastAPI                  |
| Testes           | pytest                                       |

---

## Pré-requisitos

- Python 3.11+
- PostgreSQL 14+ com extensão `pgvector` habilitada
- `cmake` e bibliotecas de compilação para o `dlib` (requerido pelo `face_recognition`)

**No Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install -y cmake build-essential libopenblas-dev liblapack-dev
```

**No macOS (Homebrew):**
```bash
brew install cmake openblas
```

---

## Instalação e Configuração

```bash
# 1. Clone o repositório
git clone <url-do-repositorio>
cd acesso-facial

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com os dados do seu banco de dados e chaves de API

# 5. Crie as tabelas no banco (rode uma vez)
python criar_banco.py

# 6. Popule o banco com dados iniciais (catracas, regras RBAC)
python seed_db.py

# 7. Inicie o servidor
uvicorn app.main:app --reload
```

A documentação interativa estará disponível em: `http://localhost:8000/docs`

---

## Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```dotenv
# Banco de Dados
DATABASE_URL=postgresql://usuario:senha@localhost:5432/acesso_facial

# Chaves de API (para autenticação dos clientes)
API_KEY_ENROLL=chave_para_cadastro_secretaria
API_KEY_ADMIN=chave_para_painel_administrativo
API_KEY_DEVICE_PREFIX=chave_dispositivo   # cada ESP32 terá sua própria chave no banco

# Segurança WebSocket
WS_ADMIN_KEY=chave_secreta_admin_123
```

> ⚠️ **Nunca commite o arquivo `.env` no repositório.** Ele já está no `.gitignore`.

---

## Como Funciona

### Fluxo de Cadastro (Enroll)

1. A secretaria envia uma foto do aluno junto com seus dados cadastrais (nome, matrícula, curso, tipo de vínculo, turno) via `POST /api/v1/access/enroll`.
2. A API extrai o vetor facial de 128 dimensões com `face_recognition`.
3. O sistema verifica se a matrícula já existe (evita duplicata).
4. O sistema verifica se o rosto já está cadastrado, comparando a distância L2 com todos os vetores existentes (threshold `< 0.45`).
5. O aluno é salvo no PostgreSQL com seu vetor biométrico indexado pelo pgvector.

### Fluxo de Verificação (Verify)

1. O ESP32-CAM captura uma foto e envia via `POST /api/v1/access/verify` com sua `API Key` e `MAC Address` no header.
2. **Etapa 1 — Extração:** A imagem passa por validação de brilho mínimo (evita fotos no escuro) e detecção de rosto único. O vetor de 128D é extraído.
3. **Etapa 2 — Busca Biométrica:** O pgvector encontra o aluno com menor distância L2 em relação ao vetor recebido.
4. **Etapa 3 — Threshold:** Se a distância L2 for maior que `0.6`, o rosto é classificado como "Desconhecido" e o acesso é bloqueado.
5. **Etapa 4 — RBAC:** As 4 regras de acesso são avaliadas em sequência.
6. **Etapa 5 — Resposta e Broadcast:** A resposta HTTP é enviada à catraca e o evento é transmitido para o painel de segurança via WebSocket.

---

## Endpoints da API

### Acesso

| Método | Rota                        | Autenticação       | Descrição                              |
|--------|-----------------------------|--------------------|----------------------------------------|
| POST   | `/api/v1/access/enroll`     | `X-API-Key-Enroll` | Cadastra um novo aluno com foto        |
| POST   | `/api/v1/access/verify`     | `X-API-Key-Device` + `X-Device-MAC` | Verifica acesso pela catraca |

### Administração

| Método | Rota                           | Descrição                                |
|--------|--------------------------------|------------------------------------------|
| GET    | `/api/v1/admin/devices`        | Lista todas as catracas e seus status    |
| GET    | `/api/v1/admin/overrides`      | Lista todas as regras de exceção         |
| POST   | `/api/v1/admin/overrides`      | Cria uma regra de exceção para um aluno  |
| DELETE | `/api/v1/admin/overrides/{id}` | Remove uma regra de exceção              |

### Testes / Utilitários

| Método | Rota                           | Descrição                                            |
|--------|--------------------------------|------------------------------------------------------|
| GET    | `/teste-alunos`                | Lista todos os alunos cadastrados                    |
| POST   | `/teste-identify`              | Identifica por vetor JSON (sem imagem, para Postman) |
| POST   | `/teste-identify-with-image`   | Identifica por imagem sem autenticação de dispositivo|

---

## Sistema RBAC

O controle de acesso segue o princípio **Fail-Secure**: se não houver regra explícita de permissão, o acesso é negado. As 4 regras são avaliadas **em sequência**:

```
Regra 1: Bloqueio Administrativo
  → O aluno está com status "BLOQUEADO" no banco? → NEGA (BLOQUEIO_ADMINISTRATIVO)

Regra 2: Override Individual — BLOQUEAR
  → Existe uma exceção de BLOQUEIO para este aluno neste bloco? → NEGA (BLOCO_NAO_PERMITIDO)

Regra 3: Override Individual — PERMITIR
  → Existe uma exceção de PERMISSÃO para este aluno neste bloco? → LIBERA

Regra 4: Regra Padrão do Vínculo
  → O tipo de vínculo do aluno (GRADUACAO, PROFESSOR, etc.) tem permissão neste bloco? → LIBERA ou NEGA
```

**Tipos de Vínculo:** `GRADUACAO` | `POS_GRADUACAO` | `PROFESSOR` | `FUNCIONARIO`

**Blocos:** `SEDE` | `BLOCO_AULAS`

---

## WebSocket — Feed em Tempo Real

O painel de segurança pode se conectar ao feed de eventos em tempo real:

```
ws://localhost:8000/api/v1/ws/feed?api_key=SUA_CHAVE_ADMIN
```

**Payload de evento recebido:**
```json
{
  "id": "evt-1712345678.123",
  "id_dispositivo": 1,
  "localizacao": "Portaria Principal",
  "ocorrido_em": "2026-04-09T14:32:10.123456",
  "distancia_l2": 0.3214,
  "id_aluno": 42,
  "nome_aluno": "João Silva",
  "resultado": "LIBERADO",
  "codigo_motivo": "ACESSO_OK"
}
```

`resultado` pode ser: `LIBERADO` | `BLOQUEADO`

`codigo_motivo` pode ser: `ACESSO_OK` | `ROSTO_NAO_RECONHECIDO` | `BLOQUEIO_ADMINISTRATIVO` | `BLOCO_NAO_PERMITIDO` | `ERRO_INTERNO`

---

## Testes

```bash
# Executa toda a suíte de testes
pytest

# Com verbose
pytest -v

# Apenas um módulo
pytest tests/test_face_service.py
```

**Cobertura atual dos testes:**
- `test_face_service.py` — Extração de vetor, serialização round-trip, detecção de erro sem face
- `test_faiss_service.py` — Busca vetorial e threshold
- `test_robustez.py` — Imagens de baixa qualidade, múltiplos rostos, imagem escura

---

## Estrutura do Projeto

```
acesso-facial/
├── app/
│   ├── main.py              # Rotas FastAPI, WebSocket e lógica principal
│   ├── models.py            # Modelos SQLAlchemy (Aluno, Dispositivo, Evento, etc.)
│   ├── schemas.py           # Schemas Pydantic (validação e serialização)
│   ├── database.py          # Conexão com o PostgreSQL
│   ├── config.py            # Configurações via variáveis de ambiente
│   ├── middleware/
│   │   └── auth.py          # Dependências de autenticação por API Key e MAC
│   └── services/
│       ├── face_service.py  # Extração e serialização do vetor facial (dlib)
│       ├── vision_service.py# Adaptador entre bytes da imagem e face_service
│       ├── faiss_service.py # Serviço de busca vetorial com FAISS (versão legada)
│       └── rbac_service.py  # Motor de regras RBAC (4 regras em sequência)
├── tests/
│   ├── fixtures/            # Imagens de teste (rostos, paisagens, baixa qualidade)
│   ├── test_face_service.py
│   ├── test_faiss_service.py
│   └── test_robustez.py
├── api.py                   # Versão simplificada da API com FAISS (protótipo inicial)
├── seed_db.py               # Popula o banco com catracas e regras RBAC
├── seed_ia.py               # Popula o banco biométrico com alunos de teste
├── requirements.txt
├── pytest.ini
└── .env                     # Variáveis de ambiente (não versionar)
```

---

## Equipe

Projeto desenvolvido como trabalho universitário para a **ExpoTech**.

Colaboradores identificados nas branches do repositório:
- **João** — Módulo de IA (face_service, vision_service, FAISS)
- **Ian** — Backend principal (rotas, banco de dados, RBAC)
- **Hericles e Julia** — Dashboard / Frontend (consumidor do WebSocket)
- **Gleice** - Modelagem de Dados e BD

---

## Licença

Este projeto foi desenvolvido para fins acadêmicos.
