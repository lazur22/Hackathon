# ⭐ Missão SJP — gestão de tarefas com gamificação e IA local

Hackathon SJP · Soluções Inovadoras para a Gestão Pública (Govtechs). Plataforma genérica de gestão de tarefas para qualquer setor da Prefeitura de São José dos Pinhais, com:
- **Fluxo completo**: demanda → atribuição → execução em campo (celular) → impedimentos → conclusão → **confirmação do demandante** (por link, sem login).
- **Integração com o legado** (Help Desk): entrada por API idempotente e saída por fila com reenvio (se o legado cair, nada se perde).
- **Gamificação transparente**: pontos por complexidade, qualidade (nota do demandante), SLA, colaboração; ranking por pessoa/equipe/setor; período mensal com reinício que preserva histórico; regras editáveis.
- **IA local** (Naive Bayes + regras; LLM opcional via Ollama): classifica, sugere prioridade, pergunta o que falta, resume e aponta impedimentos recorrentes — sempre como **sugestão** que um humano aceita ou rejeita.
- **Soberania**: nada sai do servidor da prefeitura (Lei 4.715/2025); sem CDN, sem fontes externas, sem APIs de nuvem.

## Subir (1 comando)
```bash
docker compose up --build
```
| URL | O que é |
|---|---|
| http://localhost:8000 | Início (links para tudo) |
| http://localhost:8000/web/ | Painel: gestor, atendente, demandante |
| http://localhost:8000/m/ | App do executor (PWA, celular) |
| http://localhost:9000 | Help Desk legado **simulado** |
| http://localhost:8000/docs | API (OpenAPI) |

Sem Docker: `pip install -r requirements.txt && uvicorn app.main:app --port 8000` e, em outro terminal, `cd legado && uvicorn main:app --port 9000`.

**Usuários de demonstração** (senha `demo123`): `gestor`, `gestor2`, `atendente1`, `exec1`…`exec9`, `dem1`…`dem5`, `admin`.

## Testes
`pip install pytest && python -m pytest -q` — jornada completa, permissões, impedimentos, idempotência, fila com reenvio, pontos, período, setor novo, IA.

## Documentação
`docs/ARQUITETURA.md` · `docs/DEPLOY.md` · `docs/LICENCAS.md` · `docs/LIMITACOES.md` · `docs/ROTEIRO_DEMO_E_PITCH.md` · `docs/DIVISAO_EQUIPE.md`
