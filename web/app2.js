/* Missão SJP — web, parte 2: gamificação, configuração, IA, integração, indicadores. */

// ------------------------------------------------------------------ gamificação
let GAM = { escopo: "individual", periodo: "ativo" };

V.gamificacao = async () => {
  const [eu, pers, reg] = await Promise.all([SJP.get("/api/v1/gamificacao/eu"), SJP.get("/api/v1/gamificacao/periodos"), SJP.get("/api/v1/gamificacao/regras")]);
  const q = new URLSearchParams({ escopo: GAM.escopo });
  if (GAM.periodo === "acumulado") q.set("acumulado", "true"); else if (GAM.periodo !== "ativo") q.set("periodo_id", GAM.periodo);
  const rk = await SJP.get("/api/v1/gamificacao/ranking?" + q);
  const n = eu.nivel, max = Math.max(1, ...rk.itens.map(i => i.pontos));
  const R = reg.regras; R.bonus = R.bonus_sla.pontos; R.apoio = R.colaboracao.pontos_apoio; R.imp = R.impedimento.pontos_registro_justificado; R.reab = R.reabertura.penalidade;
  const html = `<h1>🏆 Gamificação</h1>
  <div class="grid g2">
    <section class="card" aria-label="Meu perfil">
      <h2>${esc(eu.usuario.avatar || "🙂")} ${esc(eu.usuario.nome)}</h2>
      <p class="mut">Nível ${n.nivel} — <b>${esc(n.nome)}</b> · ${n.xp} XP${n.proximo_xp ? ` · próximo: ${esc(n.proximo_nome)} (${n.proximo_xp} XP)` : " · nível máximo"}</p>
      <div class="barra" role="progressbar" aria-valuenow="${Math.round(n.progresso * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.round(n.progresso * 100)}%"></i></div>
      <p>Neste período (${esc(eu.periodo.nome)}): <b>${eu.pontos_periodo} pontos</b>${eu.posicao ? ` · posição <b>${eu.posicao}º</b>` : ""}</p>
      <div class="row">${eu.catalogo_conquistas.map(c => `<span class="medalha ${c.obtida ? "" : "off"}" title="${esc(c.nome)} — ${esc(c.descricao)}${c.obtida ? "" : " (ainda não conquistada)"}" role="img" aria-label="${esc(c.nome)}${c.obtida ? "" : ", bloqueada"}">${c.icone}</span>`).join("")}</div>
      <p class="peq mut">Passe o mouse (ou foque) nas medalhas para ver como conquistar.</p>
      <button class="sec" id="btnExtrato">Ver extrato explicado dos meus pontos</button>
    </section>
    <section class="card" aria-label="Como a pontuação funciona">
      <h2>Como se ganha ponto</h2>
      <ul class="peq" style="padding-left:1.1rem;margin:.2rem 0">
        <li><b>${R.pontos_base} pontos base</b> × complexidade (baixa ${R.complexidade.baixa} · média ${R.complexidade.media} · alta ${R.complexidade.alta}).</li>
        <li><b>${Math.round(R.fracao_na_conclusao * 100)}%</b> na conclusão informada pelo executor; o restante só quando o demandante confirma, <b>ajustado pela nota</b> (qualidade, não só velocidade).</li>
        <li>Bônus de <b>${R.bonus}</b> por iniciar dentro do prazo (SLA) · <b>${R.apoio}</b> por apoiar um colega · <b>${R.imp}</b> por registrar impedimento justificado.</li>
        <li>Reabertura sem impedimento externo: <b>${R.reab}</b>.</li>
        <li>Placar <b>${esc(R.periodo)}</b>; o histórico nunca é apagado ao reiniciar.</li>
      </ul>
    </section>
  </div>
  <section class="card" style="margin-top:1rem">
    <div class="row"><h2 class="sp">Ranking — ${esc(rk.periodo.nome)}</h2>
      <label class="sr" for="selPer">Período</label>
      <select id="selPer" style="width:auto"><option value="ativo">Período atual</option>${pers.filter(p => !p.ativo).map(p => `<option value="${p.id}">${esc(p.nome)}</option>`).join("")}<option value="acumulado">Todo o histórico</option></select>
      ${SJP.tem("gestor") ? '<button class="sec" id="btnEnc">Reiniciar placar</button>' : ""}</div>
    <div class="pill-nav" role="group" aria-label="Escopo do ranking">${[["individual", "Pessoas"], ["equipe", "Equipes"], ["setor", "Setores"]].map(([k, t]) => `<button aria-pressed="${GAM.escopo === k}" data-e="${k}">${t}</button>`).join("")}</div>
    ${rk.itens.length ? rk.itens.map(i => `<div class="rk"><span class="n">${i.posicao}º</span><div><b>${esc(i.avatar || "")} ${esc(i.nome)}</b> <span class="mut peq">${esc(i.equipe || "")}${i.membros ? ` · ${i.membros} pessoas` : ""} · ${i.missoes} missões</span>
      <div class="barra"><i style="width:${Math.round(100 * Math.max(0, i.pontos) / max)}%"></i></div></div><b>${i.pontos} pts</b></div>`).join("") : '<p class="mut">Ainda não há pontos neste período.</p>'}
  </section>
  ${SJP.tem("gestor") ? `<section class="card" style="margin-top:1rem"><h2>⚙️ Regras configuráveis (gestor)</h2>
    <p class="peq mut">As regras ficam no banco e valem para todos os setores. Alterar não reescreve pontos já concedidos.</p>
    <form id="fRegras" class="grid g3">
      ${[["pontos_base", "Pontos base", R.pontos_base], ["fracao_na_conclusao", "Fração na conclusão (0–1)", R.fracao_na_conclusao], ["bonus", "Bônus SLA", R.bonus], ["apoio", "Pontos por apoio", R.apoio], ["imp", "Impedimento justificado", R.imp], ["reab", "Reabertura (negativo)", R.reab]]
        .map(([k, t, v]) => `<div><label for="r_${k}">${t}</label><input id="r_${k}" name="${k}" type="number" step="any" value="${v}"></div>`).join("")}
      <div><label for="r_per">Período do placar</label><select id="r_per" name="periodo"><option value="mensal" ${R.periodo === "mensal" ? "selected" : ""}>Mensal (automático)</option><option value="manual" ${R.periodo !== "mensal" ? "selected" : ""}>Manual</option></select></div>
    </form><div class="row" style="margin-top:.8rem"><button id="salvaRegras">Salvar regras</button><span id="regMsg" class="peq" role="status"></span></div></section>` : ""}`;
  return { html, depois() {
    $("#selPer").value = GAM.periodo;
    $("#selPer").onchange = e => { GAM.periodo = e.target.value; rotear(true); };
    $$("[data-e]").forEach(b => b.onclick = () => { GAM.escopo = b.dataset.e; rotear(true); });
    $("#btnExtrato").onclick = async () => {
      const pts = await SJP.get("/api/v1/gamificacao/pontos?limite=40");
      modal("Extrato dos meus pontos", pts.length ? `<table><tr><th>Quando</th><th>Pts</th><th>Por quê</th></tr>${pts.map(p => `<tr><td>${fdt(p.em)}</td><td class="${p.pontos < 0 ? "erro" : "okc"}"><b>${p.pontos > 0 ? "+" : ""}${p.pontos}</b></td><td>${esc(p.explicacao)}</td></tr>`).join("")}</table>` : "<p>Sem lançamentos ainda.</p>");
    };
    const enc = $("#btnEnc");
    if (enc) enc.onclick = () => modal("Reiniciar o placar?", "<p>Um novo período começa do zero. <b>O histórico e o XP/níveis são preservados</b>; o período atual fica consultável.</p><label for='np'>Nome do próximo período (opcional)</label><input id='np' name='nome'>", "Reiniciar", async fd => {
      await SJP.post("/api/v1/gamificacao/periodos/encerrar", { nome_proximo: fd.get("nome") || null }); toast("Novo período iniciado."); rotear();
    });
    const sv = $("#salvaRegras");
    if (sv) sv.onclick = async () => {
      const fd = new FormData($("#fRegras")), n = k => Number(fd.get(k));
      const o = { pontos_base: n("pontos_base"), fracao_na_conclusao: n("fracao_na_conclusao"), bonus_sla: { pontos: n("bonus") },
        colaboracao: { pontos_apoio: n("apoio") }, impedimento: { pontos_registro_justificado: n("imp") }, reabertura: { penalidade: n("reab") }, periodo: fd.get("periodo") };
      try { await SJP.put("/api/v1/gamificacao/regras", { regras: o }); $("#regMsg").textContent = "✔ Regras salvas."; $("#regMsg").className = "peq okc"; }
      catch (e) { $("#regMsg").textContent = e.message; $("#regMsg").className = "peq erro"; }
    };
  } };
};

// ------------------------------------------------------------------ configuração (cadastros genéricos)
V.cadastros = async () => {
  ESTR = await SJP.get("/api/v1/cadastros/estrutura");
  const usuarios = await SJP.get("/api/v1/cadastros/usuarios");
  const setor = id => ESTR.setores.find(s => s.id === id)?.nome || "—";
  const html = `<h1>⚙️ Configuração</h1>
  <p class="mut">A plataforma é genérica: qualquer setor da prefeitura pode ser cadastrado com suas equipes e tipos de tarefa — sem programar.</p>
  <div class="grid g2">
    <section class="card"><h2>Setores</h2><ul>${ESTR.setores.map(s => `<li><b>${esc(s.nome)}</b> ${s.sigla ? `(${esc(s.sigla)})` : ""}</li>`).join("")}</ul>
      <button class="sec" id="nSetor">+ Novo setor</button></section>
    <section class="card"><h2>Equipes</h2><ul>${ESTR.equipes.map(e => `<li>${esc(e.nome)} <span class="mut peq">· ${esc(setor(e.setor_id))}</span></li>`).join("")}</ul>
      <button class="sec" id="nEquipe">+ Nova equipe</button></section>
  </div>
  <section class="card" style="margin-top:1rem"><h2>Tipos de tarefa (fluxos)</h2>
    <div style="overflow:auto"><table><tr><th>Tipo</th><th>Setor</th><th>Complex.</th><th>SLA início</th><th>Evidência</th><th>Validação</th><th></th></tr>
    ${ESTR.tipos.map(t => `<tr><td><b>${esc(t.nome)}</b><br><span class="mut peq">${esc(t.equipe_padrao || "sem equipe padrão")}</span></td><td>${esc(t.setor)}</td><td>${esc(t.complexidade)}</td><td>${SJP.dur(t.sla_inicio_min)}</td>
      <td>${t.exige_evidencia ? "📷 exige" : "—"}</td><td>${t.exige_validacao ? "✔ demandante" : "—"}</td><td><button class="sec" data-t="${t.id}">Editar</button></td></tr>`).join("")}</table></div>
    <button style="margin-top:.6rem" id="nTipo">+ Novo tipo de tarefa</button></section>
  <section class="card" style="margin-top:1rem"><h2>Usuários (${usuarios.length})</h2>
    <div style="overflow:auto"><table><tr><th>Nome</th><th>Login</th><th>Perfis</th><th>Equipe</th></tr>${usuarios.map(u => `<tr><td>${esc(u.avatar || "")} ${esc(u.nome)}</td><td>${esc(u.login)}</td><td>${(u.perfis || []).map(p => `<span class="badge">${esc(p)}</span>`).join("")}</td><td>${esc(u.equipe || "—")}</td></tr>`).join("")}</table></div></section>`;
  const optS = ESTR.setores.map(s => `<option value="${s.id}">${esc(s.nome)}</option>`).join("");
  const optE = '<option value="">—</option>' + ESTR.equipes.map(e => `<option value="${e.id}">${esc(e.nome)}</option>`).join("");
  const tipoForm = (t = {}) => `<label for="tn">Nome</label><input id="tn" name="nome" value="${esc(t.nome || "")}" ${t.id ? "disabled" : "required"}>
    ${t.id ? "" : `<label for="ts">Setor</label><select id="ts" name="setor_id">${optS}</select>`}
    <label for="te">Equipe padrão</label><select id="te" name="equipe_padrao_id">${optE}</select>
    <label for="tc">Complexidade</label><select id="tc" name="complexidade">${["baixa", "media", "alta"].map(c => `<option ${t.complexidade === c ? "selected" : ""}>${c}</option>`).join("")}</select>
    <label for="tm">SLA para iniciar (minutos)</label><input id="tm" name="sla_inicio_min" type="number" min="5" value="${t.sla_inicio_min || 240}">
    <label><input type="checkbox" name="exige_evidencia" style="width:auto;min-height:0" ${t.exige_evidencia ? "checked" : ""}> Exige evidência (foto) para concluir</label>
    <label><input type="checkbox" name="exige_validacao" style="width:auto;min-height:0" ${t.exige_validacao !== false ? "checked" : ""}> Exige validação do demandante</label>`;
  const corpoTipo = fd => ({ equipe_padrao_id: fd.get("equipe_padrao_id") ? Number(fd.get("equipe_padrao_id")) : null, complexidade: fd.get("complexidade"),
    sla_inicio_min: Number(fd.get("sla_inicio_min")), exige_evidencia: fd.get("exige_evidencia") === "on", exige_validacao: fd.get("exige_validacao") === "on" });
  return { html, depois() {
    $("#nSetor").onclick = () => modal("Novo setor", '<label for="sn1">Nome</label><input id="sn1" name="nome" required><label for="sn2">Sigla</label><input id="sn2" name="sigla">', "Criar", async fd => { await SJP.post("/api/v1/cadastros/setores", { nome: fd.get("nome"), sigla: fd.get("sigla") || "" }); toast("Setor criado."); rotear(); });
    $("#nEquipe").onclick = () => modal("Nova equipe", `<label for="en">Nome</label><input id="en" name="nome" required><label for="es">Setor</label><select id="es" name="setor_id">${optS}</select>`, "Criar", async fd => { await SJP.post("/api/v1/cadastros/equipes", { nome: fd.get("nome"), setor_id: Number(fd.get("setor_id")) }); toast("Equipe criada."); rotear(); });
    $("#nTipo").onclick = () => modal("Novo tipo de tarefa", tipoForm(), "Criar", async fd => { await SJP.post("/api/v1/cadastros/tipos", { nome: fd.get("nome"), setor_id: Number(fd.get("setor_id")), ...corpoTipo(fd) }); toast("Tipo criado."); rotear(); });
    $$("[data-t]").forEach(b => b.onclick = () => { const t = ESTR.tipos.find(x => x.id === Number(b.dataset.t));
      modal("Editar: " + t.nome, tipoForm(t), "Salvar", async fd => { await SJP.patch("/api/v1/cadastros/tipos/" + t.id, corpoTipo(fd)); toast("Tipo atualizado."); rotear(); });
      if (t.equipe_padrao_id) $("#te").value = t.equipe_padrao_id; });
  } };
};

// ------------------------------------------------------------------ IA
V.ia = async () => {
  const rec = await SJP.get("/api/v1/ia/impedimentos-recorrentes");
  const html = `<h1>🤖 Inteligência Artificial local</h1>
  <div class="alerta"><b>Transparência:</b> toda a IA roda <b>dentro do seu servidor</b> (nenhum dado sai para nuvem — Lei 4.715/2025). Ela só <b>sugere</b>; um humano aceita ou rejeita e a decisão fica registrada na linha do tempo.</div>
  <div class="grid g2" style="margin-top:1rem">
    <section class="card"><h2>Laboratório de triagem</h2>
      <p class="peq mut">Digite um chamado como o atendente faria e veja a classificação, a prioridade e as perguntas de lacuna.</p>
      <label for="lt">Título</label><input id="lt"><label for="ld">Descrição</label><textarea id="ld"></textarea>
      <div class="row" style="margin-top:.5rem"><button class="sec" data-ex="Sem internet na recepção|Desde cedo todos os computadores da recepção estão sem rede, não consigo atender os munícipes.">Exemplo: rede</button>
      <button class="sec" data-ex="Ar condicionado pingando|O ar condicionado da sala 3 está pingando água no chão e não gela.">Exemplo: predial</button></div>
      <div id="labOut" style="margin-top:.8rem" aria-live="polite"></div></section>
    <section class="card"><h2>O que é real e o que é simulado</h2>
      <p><span class="tag-real">REAL</span> Classificador Naive Bayes treinado no servidor · regras de prioridade · detecção de lacunas · resumo da execução · agregação de impedimentos recorrentes.</p>
      <p><span class="tag-sim">SIMULADO</span> Corpus de treino sintético (chamados fictícios) — em produção seria retreinado com o histórico real do Help Desk, anonimizado.</p>
      <p><span class="tag-sim">OPCIONAL</span> LLM local via Ollama (variável <code>OLLAMA_URL</code>) para redação do resumo; sem ele, usa modelo por regras.</p></section>
  </div>
  <section class="card" style="margin-top:1rem"><h2>Impedimentos recorrentes</h2><p class="peq mut">${esc(rec.como_funciona)}</p>
    ${rec.itens.length ? rec.itens.map(r => `<div class="card" style="margin:.5rem 0"><b>${esc(SJP.IMP[r.tipo] || r.tipo)}</b> — ${r.ocorrencias} ocorrência(s), ${r.abertos} em aberto
      ${r.termos_frequentes.length ? `<br><span class="peq mut">Termos frequentes: ${r.termos_frequentes.map(t => `${esc(t.termo)} (${t.ocorrencias})`).join(", ")}</span>` : ""}
      ${r.sugestao ? `<br><span class="peq">💡 ${esc(r.sugestao)}</span>` : ""}</div>`).join("") : '<p class="mut">Sem impedimentos registrados ainda.</p>'}</section>`;
  return { html, depois() {
    let to; const rodar = () => { clearTimeout(to); to = setTimeout(async () => {
      if (($("#lt").value + $("#ld").value).trim().length < 8) return;
      const r = await SJP.post("/api/v1/ia/analisar", { titulo: $("#lt").value, descricao: $("#ld").value });
      $("#labOut").innerHTML = `<div class="ia-box"><h3>Classificação</h3>${r.classificacao.map(c => `<div>${esc(c.rotulo)} → ${esc(c.equipe)} <b>${Math.round(c.confianca * 100)}%</b><div class="barra"><i style="width:${Math.round(c.confianca * 100)}%"></i></div></div>`).join("")}
        <p>Prioridade: <b>${SJP.PRIO[r.prioridade.valor]}</b><br><span class="peq mut">${r.prioridade.motivos.map(esc).join("; ")}</span></p>
        ${r.lacunas.length ? `<b>Perguntas:</b><ul>${r.lacunas.map(l => `<li>${esc(l.pergunta)}</li>`).join("")}</ul>` : ""}</div>`;
    }, 400); };
    $("#lt").oninput = rodar; $("#ld").oninput = rodar;
    $$("[data-ex]").forEach(b => b.onclick = () => { const [t, d] = b.dataset.ex.split("|"); $("#lt").value = t; $("#ld").value = d; rodar(); });
  } };
};

// ------------------------------------------------------------------ integração
V.integracao = async () => {
  const [sis, ob] = await Promise.all([SJP.get("/api/v1/integracao/sistemas"), SJP.get("/api/v1/integracao/outbox?limite=40")]);
  const html = `<h1>🔌 Integração com sistemas legados</h1>
  <p class="mut">Entrada: o legado envia chamados por API (idempotente). Saída: cada mudança de status vira uma mensagem numa fila (outbox) com reenvio automático — se o legado cair, nada se perde e a ordem é mantida.</p>
  <div class="grid g2">${sis.map(s => `<section class="card"><h2>${esc(s.nome)} <span class="badge leg">${esc(s.codigo)}</span></h2>
    <p class="peq">Webhook: <code>${esc(s.webhook_url || "—")}</code></p>
    <div class="row"><div class="kpi"><b>${s.tarefas_recebidas}</b><span>chamados recebidos</span></div><div class="kpi"><b>${s.mensagens_enviadas}</b><span>status devolvidos</span></div>
    <div class="kpi"><b class="${s.mensagens_pendentes ? "erro" : "okc"}">${s.mensagens_pendentes}</b><span>na fila</span></div></div></section>`).join("")}</div>
  <section class="card" style="margin-top:1rem"><div class="row"><h2 class="sp">Fila de saída (outbox)</h2><button id="btnSync">🔄 Sincronizar agora</button></div>
    <div style="overflow:auto"><table><tr><th>#</th><th>Tarefa</th><th>Status legado</th><th>Situação</th><th>Tentativas</th><th>Detalhe</th></tr>
    ${ob.map(o => `<tr><td>${o.id}</td><td><a href="#/tarefa/${o.tarefa_id}">${o.tarefa_id}</a></td><td>${esc(o.status_legado || o.evento)}</td>
      <td>${o.status === "enviado" ? "✅ enviado" : "⏳ pendente"}</td><td>${o.tentativas}</td><td class="peq">${o.status === "enviado" ? fdt(o.enviado_em) : esc(o.ultimo_erro || "aguardando")}</td></tr>`).join("") || '<tr><td colspan="6" class="mut">Nada na fila.</td></tr>'}</table></div></section>
  <section class="card" style="margin-top:1rem"><h2>Contrato da API de entrada</h2>
<pre class="cod">curl -X POST ${location.origin}/api/v1/integracao/tarefas \\
  -H "X-API-Key: &lt;chave do sistema&gt;" -H "Content-Type: application/json" \\
  -d '{"id_origem":"HD-1042","titulo":"Sem rede na recepção","descricao":"...",
       "solicitante_nome":"Patrícia Souza","local":"Prédio A","status_origem":"ABERTO"}'
# Reenviar o mesmo id_origem não duplica: devolve a tarefa existente (idempotência).</pre></section>`;
  return { html, depois() {
    $("#btnSync").onclick = async () => { try { const r = await SJP.post("/api/v1/integracao/sincronizar"); toast(`Fila processada: ${r.enviados ?? 0} enviada(s), ${r.falhas ?? 0} falha(s).`); rotear(true); } catch (e) { toast(e.message); } };
  } };
};

// ------------------------------------------------------------------ indicadores
function grafSemanal(dados) {
  if (!dados.length) return '<p class="mut">Sem dados na janela.</p>';
  const W = 640, H = 200, p = 30, m = Math.max(1, ...dados.flatMap(d => [d.abertas, d.resolvidas])), bw = (W - 2 * p) / dados.length;
  const barras = dados.map((d, i) => { const x = p + i * bw, h1 = (H - 2 * p) * d.abertas / m, h2 = (H - 2 * p) * d.resolvidas / m;
    return `<rect x="${x + 4}" y="${H - p - h1}" width="${bw / 2 - 5}" height="${h1}" fill="#35d6ee"><title>${d.semana}: ${d.abertas} abertas</title></rect>
      <rect x="${x + bw / 2}" y="${H - p - h2}" width="${bw / 2 - 5}" height="${h2}" fill="#4fe0a0"><title>${d.semana}: ${d.resolvidas} resolvidas</title></rect>
      <text x="${x + bw / 2}" y="${H - 10}" text-anchor="middle">${d.semana.slice(-3)}</text>`; }).join("");
  return `<svg class="graf" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tarefas abertas e resolvidas por semana" style="width:100%;height:auto">${barras}
    <text x="${p}" y="14" style="fill:#35d6ee">■ abertas</text><text x="${p + 80}" y="14" style="fill:#4fe0a0">■ resolvidas</text></svg>`;
}

V.indicadores = async () => {
  const [d, base] = await Promise.all([SJP.get("/api/v1/indicadores?dias=90"), SJP.get("/api/v1/indicadores/baseline").catch(() => null)]);
  const val = i => i.mediana != null ? `${SJP.dur(i.mediana)}<span class="peq mut"> mediana · n=${i.amostra}</span>`
    : i.media != null ? `${i.media}<span class="peq mut"> média · n=${i.amostra}</span>`
    : i.valor && typeof i.valor === "object" ? Object.entries(i.valor).map(([k, v]) => `${esc(SJP.STATUS[k]?.[1] || SJP.IMP[k] || k)}: <b>${v}</b>`).join(" · ") || "—"
    : i.valor != null ? `${i.valor}${i.taxa != null ? ` <span class="peq mut">(${i.taxa}% das tarefas)</span>` : ""}`
    : i.executores_ativos != null ? `${i.executores_ativos} servidores · ${i.participacoes_como_apoio} apoios` : "—";
  const html = `<h1>📈 Indicadores</h1><p class="mut">Janela: últimos ${d.janela_dias} dias · ${d.total} tarefas. Cada indicador explica o que mede e de onde vem.</p>
  <div class="grid g2">${d.indicadores.map(i => `<section class="card"><h3>${esc(i.nome)}</h3><div style="font-size:1.25rem;font-weight:700;color:var(--cian)">${val(i)}</div>
    <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(i.mede)}<br><span class="mut">Fonte: ${esc(i.fonte)}</span></p></details></section>`).join("")}</div>
  <section class="card" style="margin-top:1rem"><h2>Evolução semanal</h2>${grafSemanal(d.evolucao_semanal)}</section>
  <section class="card" style="margin-top:1rem"><h2>Linha de base real do Help Desk</h2>
    ${base ? `<p class="peq mut">Dados agregados, sem informação pessoal — retrato de <b>antes</b> da plataforma, para medir o ganho depois.</p><pre class="cod">${esc(JSON.stringify(base, null, 2))}</pre>`
      : '<p class="mut">Baseline ainda não gerada (<code>python scripts/gerar_baseline.py</code>).</p>'}</section>`;
  return html;
};
