# O que é real e o que é simulado
| Item | Situação |
|---|---|
| Fluxo de tarefas, permissões, auditoria, validação por link | **Real** (testado automaticamente) |
| API de integração e fila de saída com reenvio | **Real** |
| Help Desk legado | **Simulado** (`legado/`), imitando o vocabulário de status do real |
| Dados (pessoas, chamados, histórico) | **Fictícios** (`app/seed.py`) |
| Classificador de IA | **Real**, mas treinado em corpus **sintético**; em produção, retreinar com histórico real anonimizado |
| LLM (Ollama) | Opcional, não obrigatório |
| Web Push | Implementado, **não validado** com serviço externo; notificações no app (SSE) são o caminho principal |
| Geolocalização no "Iniciar" | Real no navegador (exige HTTPS fora de localhost) |
| Offline do app | Apenas abrir o app e enfileirar ações de texto; fotos exigem conexão |
| Linha de base do Help Desk | **Placeholder** até receber o CSV real (`scripts/gerar_baseline.py`) |
| Autenticação | Senhas + token de sessão simples; produção deve integrar ao diretório (LDAP/SSO) da prefeitura |
