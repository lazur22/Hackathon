# Arquitetura

```
 Help Desk legado ──POST /integracao/tarefas (X-API-Key, idempotente)──▶ ┌──────────────────────────┐
        ▲                                                                │  FastAPI (Python)         │
        └──── webhook de status (Outbox: fila, retry, ordem por tarefa) ◀─┤  workflow · gamificação  │
 Painel web (gestor/atendente/demandante) ──REST──────────────────────▶ │  IA local · notificações │
 App PWA do executor ──REST + SSE (+Web Push opcional)────────────────▶ └────────────┬─────────────┘
 Link do demandante (sem login) ──────────────────────────────────────▶   SQLite │ PostgreSQL + uploads
```

## Decisões
- **Máquina de estados** única (`app/services/workflow.py`): NOVA → ATRIBUIDA → EM_ANDAMENTO ⇄ BLOQUEADA → CONCLUIDA_EXECUTOR → RESOLVIDA | PENDENTE (volta ao fluxo) | CANCELADA. "Concluída pelo executor" ≠ "resolvida pelo demandante". Toda transição gera um evento (trilha de auditoria).
- **Genérico**: setores, equipes, tipos de tarefa (SLA, complexidade, exige evidência/validação) são cadastros; criar um setor novo não exige código.
- **Integração**: idempotência por `(sistema, id_origem)` (constraint única); saída via tabela *outbox* com backoff e chave `{codigo}:{id_origem}:{seq}`; status internos mapeados para o vocabulário real do legado (ABERTO, ENCAMINHAR, EM EXECUCAO, EXECUTADO, CONCLUIDO, REABERTO, CANCELADO).
- **Gamificação**: livro-razão de pontos (`pontos`) com explicação por lançamento; 40% na conclusão do executor, restante × fator de qualidade pela nota do demandante; XP/níveis usam o histórico inteiro, o placar usa o período.
- **IA**: Naive Bayes multinomial em Python puro (12 categorias) + regras. Nenhuma sugestão altera dados sem aceite humano; aceite/rejeição fica registrado.
- **Tempo real**: SSE (sem dependências). Web Push é opcional (VAPID).
- **Acessibilidade**: ícone + texto nos status, alvos ≥ 44px, foco visível, botão A+, respeita *reduced motion*.
