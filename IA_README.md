# Módulo de IA - Documentação para Integração

As funções prontas para uso no Backend estão localizadas em:
- `app/services/face_service.py`: Extração e serialização.
- `app/services/faiss_service.py`: Gerenciamento do banco vetorial.

### Fluxos Principais:
1. **Cadastro:** `extract_face_vector(bytes)` -> `vector_to_blob(vector)` -> (Ian salva no DB).
2. **Reconhecimento:** `extract_face_vector(bytes)` -> `search_vector(vector, threshold=0.5)`.

*Atualização J-SYNC: Contrato de interface e módulos de IA entregues para integração na branch develop.*