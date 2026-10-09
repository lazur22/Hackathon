# Roteiro de demonstração (≈5 min) e pitch

**Antes**: `docker compose up`, abrir 3 abas: legado (:9000), painel (:8000/web, `gestor`), celular (:8000/m, `exec4`; ou DevTools modo celular).

1. **Dor** (30s): chamados chegam por ramal, ninguém sabe o andamento, o legado não reflete a campo.
2. **Entrada pelo legado** (40s): no legado, botão de exemplo "rede" → chamado aparece sozinho no painel. Mostrar o selo de origem e a **sugestão de IA** (equipe, prioridade, perguntas).
3. **Atribuição** (30s): gestor aceita a IA (fica registrado) e atribui ao executor.
4. **Execução no celular** (60s): executor recebe aviso em tempo real, inicia (localização), registra foto, **registra impedimento** → painel mostra ⛔ e o legado muda para o status correspondente.
5. **Conclusão e confirmação** (45s): resolver impedimento, concluir; abrir o **link do demandante** (sem login), dar 5★.
6. **Gamificação** (45s): pontos em duas etapas, extrato explicado, ranking por pessoa/equipe/setor, reiniciar placar preservando histórico.
7. **Resiliência** (30s): "simular queda" no legado, mudar status, voltar o legado → fila entrega na ordem, sem duplicar.
8. **Generalidade e soberania** (30s): cadastrar um setor novo em Configuração; mostrar que tudo roda local, sem nuvem.

**Mensagem final**: não trocamos o sistema da prefeitura — damos visibilidade, engajamento e inteligência por cima dele, dentro da lei de soberania de dados.

**Perguntas prováveis**: "e se o legado cair?" (outbox) · "a IA decide?" (não, só sugere) · "gamificação não vira corrida por quantidade?" (qualidade pesa mais; impedimento justificado não penaliza) · "isso escala a outras secretarias?" (cadastros genéricos, testado).
Ajuste os tempos e a ordem à seção 19 do Manual e aos critérios do edital.
