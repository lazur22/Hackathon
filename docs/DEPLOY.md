# Implantação on-premises

1. **Requisitos**: Docker + Compose (ou Python 3.12+). Sem acesso externo em tempo de execução.
2. **Produção**: defina `SEED_ON_START=0`, `BASE_URL=https://<host interno>`, e `DATABASE_URL=postgresql+psycopg://...` (instale `psycopg[binary]`). Troque a senha dos usuários e a chave `X-API-Key` do sistema legado.
3. **HTTPS**: coloque um proxy reverso (nginx/Caddy) à frente. HTTPS é necessário para geolocalização e Web Push fora de `localhost`.
4. **Dados**: volumes `dados` (banco) e `anexos` (fotos). Faça backup de ambos.
5. **IA com LLM local (opcional)**: `docker compose --profile ia up`, `ollama pull llama3.2:3b`, defina `OLLAMA_URL=http://ollama:11434`. Sem isso, a IA funciona por modelos locais próprios.
6. **Integrar o Help Desk real**: cadastre o sistema (código, `api_key`, `webhook_url`) e faça o legado chamar `POST /api/v1/integracao/tarefas`; receba os status em `webhook_url`.
7. **Push sem terceiros** (futuro): Web Push passa pelos serviços do fabricante do navegador; para soberania total, usar ntfy/UnifiedPush self-hosted. As notificações dentro do app (SSE) não dependem disso.
