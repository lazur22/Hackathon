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
  <section class="card" style="margin-top:1rem"><h2>📚 Ensinar o assistente de suporte</h2>
    <p class="peq mut">Ele já aprende sozinho com cada OS concluída (problema + o que foi feito) e com o 👍/👎 dos usuários. Aqui você cadastra um procedimento novo.</p>
    <form id="fKb"><label for="kt">Título do problema</label><input id="kt" required minlength="3" placeholder="Ex.: Catraca da recepção travada">
    <label for="ks">Como o usuário descreve (palavras-chave)</label><input id="ks" placeholder="catraca travada, cartão de acesso não abre">
    <label for="kp">Passos (um por linha)</label><textarea id="kp" required placeholder="Reinicie o leitor de cartão.&#10;Verifique a fonte da catraca."></textarea>
    <button style="margin-top:.6rem">Salvar procedimento</button> <span id="kMsg" class="peq" role="status"></span></form></section>
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
    $("#fKb").onsubmit = async e => { e.preventDefault();
      try { await SJP.post("/api/v1/chat/conhecimento", { titulo: $("#kt").value, sintomas: $("#ks").value, passos: $("#kp").value.split("\n").map(x => x.trim()).filter(Boolean) });
        $("#kMsg").textContent = "✔ Salvo. O assistente já usa este procedimento."; $("#kMsg").className = "peq okc"; $("#fKb").reset(); }
      catch (er) { $("#kMsg").textContent = er.message; $("#kMsg").className = "peq erro"; } };
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
  const [d, base, cf] = await Promise.all([SJP.get("/api/v1/indicadores?dias=90"), SJP.get("/api/v1/indicadores/baseline").catch(() => null), SJP.get("/api/v1/indicadores/confiabilidade")]);
  const val = i => i.mediana != null ? `${SJP.dur(i.mediana)}<span class="peq mut"> mediana · n=${i.amostra}</span>`
    : i.media != null ? `${i.media}<span class="peq mut"> média · n=${i.amostra}</span>`
    : i.valor && typeof i.valor === "object" ? Object.entries(i.valor).map(([k, v]) => `${esc(SJP.STATUS[k]?.[1] || SJP.IMP[k] || k)}: <b>${v}</b>`).join(" · ") || "—"
    : i.valor != null ? `${i.valor}${i.taxa != null ? ` <span class="peq mut">(${i.taxa}% das tarefas)</span>` : ""}`
    : i.executores_ativos != null ? `${i.executores_ativos} servidores · ${i.participacoes_como_apoio} apoios` : "—";
  const html = `<h1>📈 Indicadores</h1><p class="mut">Janela: últimos ${d.janela_dias} dias · ${d.total} tarefas. Cada indicador explica o que mede e de onde vem.</p>
  <div class="grid g2">${d.indicadores.map(i => `<section class="card"><h3>${esc(i.nome)}</h3><div style="font-size:1.25rem;font-weight:700;color:var(--cian)">${val(i)}</div>
    <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(i.mede)}<br><span class="mut">Fonte: ${esc(i.fonte)}</span></p></details></section>`).join("")}</div>
  <section class="card" style="margin-top:1rem"><h2>Evolução semanal</h2>${grafSemanal(d.evolucao_semanal)}</section>
  ${secaoConfiab(cf)}
  <section class="card" style="margin-top:1rem"><h2>Linha de base REAL do Help Desk (antes da plataforma)</h2>${blocoBase(base)}</section>`;
  return html;
};


function barrasDia(serie) {
  if (!serie.length) return '<p class="mut peq">Sem OS nos últimos 30 dias.</p>';
  const W = 640, H = 120, p = 24, m = Math.max(1, ...serie.map(x => x.n)), bw = (W - 2 * p) / serie.length;
  return `<svg class="graf" viewBox="0 0 ${W} ${H}" role="img" aria-label="OS abertas por dia nos últimos 30 dias" style="width:100%;height:auto">${serie.map((x, i) => {
    const h = (H - 2 * p) * x.n / m; return `<rect x="${p + i * bw + 2}" y="${H - p - h}" width="${Math.max(2, bw - 4)}" height="${h}" fill="#35d6ee"><title>${x.dia}: ${x.n}</title></rect>`; }).join("")}
    <text x="${p}" y="${H - 6}">${serie[0].dia.slice(5)}</text><text x="${W - p - 30}" y="${H - 6}">${serie[serie.length - 1].dia.slice(5)}</text></svg>`;
}

function secaoConfiab(c) {
  const h = v => v == null ? "—" : v;
  const e = c.avaliacoes, dist = e.distribuicao, mx = Math.max(1, ...Object.values(dist));
  const ch = c.assistente;
  return `<h2 style="margin-top:1.4rem">🛠️ Confiabilidade e qualidade do atendimento</h2>
  <div class="grid g2">
   <section class="card"><h3>OS abertas no período</h3>
     <div class="row"><div class="kpi"><b>${c.os_abertas.ultimos_7_dias}</b><span>últimos 7 dias</span></div><div class="kpi"><b>${c.os_abertas.ultimos_30_dias}</b><span>últimos 30 dias</span></div>
     <div class="kpi"><b>${c.os_abertas.variacao_percentual == null ? "—" : (c.os_abertas.variacao_percentual > 0 ? "+" : "") + c.os_abertas.variacao_percentual + "%"}</b><span>vs. 30 dias anteriores</span></div></div>
     ${barrasDia(c.os_abertas.por_dia_30d)}
     <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(c.os_abertas.mede)} Fonte: ${esc(c.os_abertas.fonte)}</p></details></section>
   <section class="card"><h3>MTTR — tempo médio de reparo</h3>
     <div class="row"><div class="kpi"><b>${h(c.mttr.horas_media)} h</b><span>média (abertura → concluída)</span></div><div class="kpi"><b>${h(c.mttr.horas_so_execucao_media)} h</b><span>só execução em campo</span></div></div>
     ${c.mttr.por_tipo.map(t => `<div class="peq">${esc(t.tipo)} <span class="mut">(n=${t.n})</span><div class="barra"><i style="width:${Math.min(100, 100 * t.horas_media / Math.max(1, c.mttr.por_tipo[0].horas_media))}%"></i></div>${t.horas_media} h</div>`).join("")}
     <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(c.mttr.mede)} Fonte: ${esc(c.mttr.fonte)}</p></details></section>
   <section class="card"><h3>MTBF — tempo médio entre falhas</h3>
     <div class="row"><div class="kpi"><b>${h(c.mtbf.dias_media)} dias</b><span>média entre falhas do mesmo ativo</span></div><div class="kpi"><b>${c.mtbf.ativos_com_reincidencia}</b><span>ativos/locais com reincidência</span></div></div>
     ${c.mtbf.piores.map(x => `<p class="peq" style="margin:.3rem 0"><b>${esc(x.ativo)}</b> · ${esc(x.tipo)}<br><span class="erro">${x.falhas} falhas, a cada ${x.mtbf_dias} dias</span> · OS ${x.os.map(i => `<a href="#/tarefa/${i}">#${i}</a>`).join(", ")}</p>`).join("") || '<p class="mut peq">Sem reincidência no período.</p>'}
     <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(c.mtbf.mede)} Fonte: ${esc(c.mtbf.fonte)}</p></details></section>
   <section class="card"><h3>Recorrência de OS (mesma descrição/necessidade)</h3>
     <div class="row"><div class="kpi"><b>${c.recorrencia.taxa_percentual}%</b><span>das OS repetem um problema</span></div><div class="kpi"><b>${c.recorrencia.os_reabertas}</b><span>OS reabertas</span></div></div>
     ${c.recorrencia.ranking.map(x => `<p class="peq" style="margin:.3rem 0"><b>${esc(x.onde)}</b> · ${esc(x.tipo)} — ${x.repeticoes} repetição(ões)<br><span class="mut">💡 ${esc(x.acao)}</span></p>`).join("") || '<p class="mut peq">Sem recorrências.</p>'}
     <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(c.recorrencia.mede)} Fonte: ${esc(c.recorrencia.fonte)}</p></details></section>
   <section class="card"><h3>Avaliações dos atendimentos</h3>
     <div class="row"><div class="kpi"><b>${h(e.media)} ★</b><span>média (n=${e.amostra})</span></div><div class="kpi"><b>${h(e.percentual_4_ou_5)}%</b><span>notas 4 ou 5</span></div></div>
     ${[5, 4, 3, 2, 1].map(n => `<div class="row peq"><span style="width:2.2rem">${n}★</span><div class="barra sp"><i style="width:${100 * dist[n] / mx}%"></i></div><span>${dist[n]}</span></div>`).join("")}
     <details><summary class="peq mut">Por equipe</summary><p class="peq">${e.por_equipe.map(x => `${esc(x.equipe)}: <b>${x.media}</b> (n=${x.n})`).join("<br>")}</p></details></section>
   <section class="card"><h3>Assistente de suporte — OS evitadas</h3>
     <div class="row"><div class="kpi"><b>${ch.perguntas}</b><span>perguntas (90 dias)</span></div><div class="kpi"><b>${ch.taxa_deflexao == null ? "—" : ch.taxa_deflexao + "%"}</b><span>resolveram sem abrir OS</span></div></div>
     <p class="peq"><b>O que o assistente ainda não sabe</b> (ensine na aba 🤖 IA):</p>${ch.lacunas_de_conhecimento.map(x => `<p class="peq" style="margin:.2rem 0">• ${esc(x.pergunta)} <span class="mut">(${x.vezes}×)</span></p>`).join("") || '<p class="mut peq">Nenhuma lacuna registrada.</p>'}
     <details><summary class="peq mut">O que mede / fonte</summary><p class="peq">${esc(ch.mede)} Fonte: ${esc(ch.fonte)}</p></details></section>
  </div>`;
}

function blocoBase(b) {
  if (!b || b.origem === "placeholder") return '<p class="mut">Linha de base não gerada (<code>python scripts/gerar_baseline.py chamados.txt</code>).</p>';
  const h = b.horas_ate_conclusao;
  return `<p class="peq mut">${esc(b.leitura)} Período: ${esc(b.periodo)}.</p>
  <div class="row"><div class="kpi"><b>${b.chamados.toLocaleString("pt-BR")}</b><span>chamados</span></div><div class="kpi"><b>${h.mediana} h</b><span>mediana até concluir</span></div>
   <div class="kpi"><b>${h.media} h</b><span>média (cauda longa)</span></div><div class="kpi"><b>${h.p90} h</b><span>90% concluem em até</span></div>
   <div class="kpi"><b>${b.percentual_conclusao_acima_de_72h}%</b><span>levam mais de 72 h</span></div><div class="kpi"><b>${b.percentual_sem_nome_de_tecnico_no_registro}%</b><span>sem técnico identificado no registro</span></div></div>
  <p class="peq">Por equipe responsável: ${Object.entries(b.por_departamento_responsavel).map(([k, v]) => `${esc(k)} <b>${v}</b>`).join(" · ")}</p>`;
}

// ------------------------------------------------------------------ rotas (gestor/atendente)
const CORES = ["#35d6ee", "#b79cff", "#ffc94d", "#4fe0a0", "#ff8a8a", "#ffb86b", "#7fb2ff"];
V.rotas = async () => {
  const r = await SJP.get("/api/v1/rota/resumo");
  const todos = [r.central, ...r.locais];
  const la = todos.map(x => x.lat), lo = todos.map(x => x.lon), W = 680, H = 440, p = 40;
  const [mnLa, mxLa, mnLo, mxLo] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
  const X = lon => p + (lon - mnLo) / ((mxLo - mnLo) || 1) * (W - 2 * p), Y = lat => H - p - (lat - mnLa) / ((mxLa - mnLa) || 1) * (H - 2 * p);
  const linhas = r.rotas.map((rt, i) => {
    const pts = [[r.central.lat, r.central.lon], ...rt.paradas.filter(x => x.lat != null).map(x => [x.lat, x.lon])];
    const cor = CORES[i % CORES.length];
    const caminho = pts.map(([a, b]) => `${X(b)},${Y(a)}`).join(" ");
    const volta = pts.length > 1 ? `<line x1="${X(pts.at(-1)[1])}" y1="${Y(pts.at(-1)[0])}" x2="${X(r.central.lon)}" y2="${Y(r.central.lat)}" stroke="${cor}" stroke-dasharray="4 5" opacity=".5"/>` : "";
    return `<polyline points="${caminho}" fill="none" stroke="${cor}" stroke-width="2.5"/>${volta}`;
  }).join("");
  const nomes = r.locais.map(l => `<circle cx="${X(l.lon)}" cy="${Y(l.lat)}" r="5" fill="#b4c3e0"/><text x="${X(l.lon) + 8}" y="${Y(l.lat) + 4}">${esc(l.nome.length > 26 ? l.nome.slice(0, 25) + "…" : l.nome)}</text>`).join("");
  const mapa = `<svg class="graf" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mapa esquemático das rotas sugeridas por técnico" style="width:100%;height:auto;background:#0a1630;border-radius:12px">
    ${linhas}${nomes}<rect x="${X(r.central.lon) - 8}" y="${Y(r.central.lat) - 8}" width="16" height="16" fill="#ffc94d"/><text x="${X(r.central.lon) + 12}" y="${Y(r.central.lat) + 4}" style="fill:#ffc94d;font-weight:700">Central</text></svg>`;
  const e = r.economia;
  const html = `<h1>🗺️ Rotas e deslocamento</h1>
  <p class="mut">Hoje, com a OS de papel, o técnico volta à central a cada atendimento. Com a OS digital ele recebe a <b>próxima missão mais perto</b> e segue direto.</p>
  <div class="alerta peq">⚠ ${esc(r.aviso)}</div>
  <div class="grid g2" style="margin-top:1rem">
   <section class="card"><h2>Economia estimada (atendimentos abertos agora)</h2>
    <div class="row"><div class="kpi"><b>${e.km_papel} km</b><span>com papel (volta à central a cada OS)</span></div><div class="kpi"><b>${e.km_digital} km</b><span>com rota por proximidade</span></div>
    <div class="kpi"><b class="okc">−${e.percentual}%</b><span>${e.km_economizados} km · ≈ R$ ${e.custo_estimado_economizado.toLocaleString("pt-BR")}</span></div></div>
    <p class="peq mut">${esc(e.premissas)}</p></section>
   <section class="card"><h2>Oportunidades de unir saídas</h2>${r.oportunidades.length ? r.oportunidades.map(o => `<p class="peq" style="margin:.4rem 0"><a href="#/tarefa/${o.a.id}">#${o.a.id} ${esc(o.a.titulo)}</a> ↔ <a href="#/tarefa/${o.b.id}">#${o.b.id} ${esc(o.b.titulo)}</a><br><b>${o.km < 0.2 ? "no mesmo local" : o.km + " km de distância"}</b> — ${esc(o.sugestao)}</p>`).join("") : '<p class="mut">Nenhuma no momento.</p>'}</section>
  </div>
  <section class="card" style="margin-top:1rem"><h2>Mapa esquemático das rotas sugeridas</h2>${mapa}
   <div class="row peq">${r.rotas.map((rt, i) => `<span><span style="color:${CORES[i % CORES.length]}">━</span> ${esc(rt.tecnico)}</span>`).join("")}<span class="mut">┅ retorno à central (uma vez só)</span></div></section>
  <section class="card" style="margin-top:1rem"><h2>Sequência sugerida por técnico</h2>${r.rotas.map(rt => `<p class="peq"><b>${esc(rt.tecnico)}</b>: ${rt.paradas.map((x, i) => `${i + 1}. <a href="#/tarefa/${x.id}">${esc(x.titulo)}</a> <span class="mut">(+${x.km} km)</span>`).join(" → ")}</p>`).join("") || '<p class="mut">Sem atendimentos abertos.</p>'}
   ${r.sem_localizacao.length ? `<p class="peq mut">Sem local cadastrado (não entram na rota): ${r.sem_localizacao.map(i => `<a href="#/tarefa/${i}">#${i}</a>`).join(", ")}</p>` : ""}</section>`;
  return html;
};

// ------------------------------------------------------------------ assistente de suporte (chat flutuante)
function montarChat() {
  if ($("#chatBtn")) return;
  document.body.insertAdjacentHTML("beforeend", `
  <button id="chatBtn" style="position:fixed;right:18px;bottom:18px;z-index:30;border-radius:99px;min-height:56px;padding:.6rem 1.1rem;box-shadow:0 6px 24px #0008" aria-haspopup="dialog">💬 Assistente</button>
  <section id="chatBox" role="dialog" aria-label="Assistente de suporte" style="display:none;position:fixed;right:18px;bottom:84px;z-index:31;width:min(400px,94vw);height:min(560px,74vh);background:var(--card);border:1px solid var(--cian);border-radius:16px;flex-direction:column;box-shadow:0 10px 40px #000a">
   <div class="row" style="padding:.6rem .8rem;border-bottom:1px solid var(--bd)"><b>🤖 Assistente de suporte</b><span class="sp"></span><button class="sec" id="chatX" style="min-height:36px" aria-label="Fechar">✕</button></div>
   <div id="chatMsgs" style="flex:1;overflow:auto;padding:.7rem" aria-live="polite"><p class="peq mut">Descreva o problema como falaria ao telefone. Eu busco procedimentos e casos parecidos já resolvidos, e só sugiro abrir OS se não resolver. Roda 100% no servidor da prefeitura.</p></div>
   <form id="chatF" class="row" style="padding:.6rem;border-top:1px solid var(--bd);flex-wrap:nowrap"><input id="chatI" placeholder="Ex.: telefone mudo no ramal 3380" autocomplete="off" aria-label="Sua pergunta"><button style="white-space:nowrap">Enviar</button></form></section>`);
  const box = $("#chatBox"), msgs = $("#chatMsgs");
  const abre = v => { box.style.display = v ? "flex" : "none"; $("#chatBtn").setAttribute("aria-expanded", v); if (v) $("#chatI").focus(); };
  $("#chatBtn").onclick = () => abre(box.style.display === "none");
  $("#chatX").onclick = () => abre(false);
  const md = t => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
  $("#chatF").onsubmit = async e => {
    e.preventDefault(); const q = $("#chatI").value.trim(); if (q.length < 3) return; $("#chatI").value = "";
    msgs.insertAdjacentHTML("beforeend", `<p style="text-align:right"><span class="badge" style="color:var(--fg);white-space:normal">${esc(q)}</span></p>`);
    try {
      const r = await SJP.post("/api/v1/chat", { mensagem: q });
      const pode = SJP.tem("gestor", "atendente");
      msgs.insertAdjacentHTML("beforeend", `<div class="ia-box peq" style="margin:.5rem 0" data-c="${r.conversa_id}">${md(r.resposta)}
        <div class="peq mut" style="margin-top:.4rem">${r.fontes.map(f => f.tipo === "os" ? `<a href="#/tarefa/${f.id}">OS #${f.id}</a>` : "procedimento").join(" · ")} · confiança ${esc(r.confianca)} · ${esc(r.modo)}</div>
        <div class="row" style="margin-top:.5rem"><button class="ok" data-r="1" style="min-height:38px">👍 Resolveu</button><button class="sec" data-r="0" style="min-height:38px">👎 Preciso de OS</button></div></div>`);
      msgs.scrollTop = msgs.scrollHeight;
      const card = msgs.lastElementChild;
      card.querySelectorAll("[data-r]").forEach(b => b.onclick = async () => {
        const ok = b.dataset.r === "1"; await SJP.post(`/api/v1/chat/${r.conversa_id}/feedback`, { resolveu: ok, abriu_os: !ok });
        card.querySelector(".row:last-child").innerHTML = ok ? '<span class="okc">✔ Ótimo! Uma OS a menos — e o assistente aprendeu com isso.</span>'
          : (pode ? '<button id="chatOS" style="min-height:38px">Abrir OS com esta descrição</button>' : '<span class="peq">Acione o atendimento do Help Desk e informe: <i>' + esc(q) + "</i></span>");
        const bo = card.querySelector("#chatOS"); if (bo) bo.onclick = () => { try { sessionStorage.setItem("preTitulo", q); } catch (x) {} abre(false); location.hash = "#/nova"; };
      });
    } catch (er) { msgs.insertAdjacentHTML("beforeend", `<p class="erro peq">${esc(er.message)}</p>`); }
  };
}
const _layoutBase = layout;
layout = function () { _layoutBase(); montarChat(); };
