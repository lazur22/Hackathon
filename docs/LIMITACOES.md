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
| Linha de base do Help Desk | **Real e agregada** (export `chamados20261005.txt`, 10.140 chamados; sem nomes). Regerar com `scripts/gerar_baseline.py` |
| Coordenadas dos locais | **Aproximadas/fictícias** na demonstração; em produção, geocodificar endereços ou usar o GPS do "Iniciar" |
| Economia de km/custo | **Estimativa** sobre as OS abertas (linha reta × 1,35; R$ 1,20/km). Não é medição; medir de verdade exige GPS ao longo de semanas |
| Assistente de suporte | **Real** (busca TF-IDF local), mas a base inicial são 7 procedimentos de exemplo + as OS **fictícias** da demonstração. Com OS reais anonimizadas ele melhora; LLM local é opcional |
| MTBF | Precisa de histórico longo e de patrimônio/local preenchidos; na demonstração usa ~3 meses fictícios |
| Qualidade das OS reais | Nas OS de papel de amostra muitas linhas têm só "N/D" ou "OS ok": o assistente **ignora** conclusões sem conteúdo (<15 caracteres) — a OS digital precisa exigir o texto do que foi feito |
| Autenticação | Senhas + token de sessão simples; produção deve integrar ao diretório (LDAP/SSO) da prefeitura |
