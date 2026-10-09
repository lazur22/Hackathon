/* Missão SJP — web (gestor, atendente, demandante). Núcleo: login, layout, rotas, painel, tarefas, detalhe, nova tarefa. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const { esc, chip, fdt, dur, toast } = SJP;
const V = {};                       // views (app2.js adiciona o restante)
let ESTR = null, naoLidas = 0, es = null, timer = null;

// ------------------------------------------------------------------ modal
function modal(titulo, corpo, okLabel, onSubmit) {
  const dlg = $("#modal");
  $("#mTitulo").textContent = titulo; $("#mCorpo").innerHTML = corpo + '<p class="erro" id="mErro" role="alert"></p>';
  $("#mOk").textContent = okLabel || "Confirmar"; $("#mOk").style.display = onSubmit ? "" : "none";
  $("#mCancelar").textContent = onSubmit ? "Cancelar" : "Fechar";
  $("#mCancelar").onclick = () => dlg.close();
  $("#mForm").onsubmit = async e => {
    e.preventDefault();
    if (!onSubmit) return dlg.close();
    $("#mOk").disabled = true;
    try { await onSubmit(new FormData($("#mForm"))); dlg.close(); }
    catch (err) { $("#mErro").textContent = err.message; }
    finally { $("#mOk").disabled = false; }
  };
  dlg.showModal();
  const f = $("input,textarea,select", $("#mCorpo")); if (f) f.focus();
}

// ------------------------------------------------------------------ boot / login
async function boot() {
  window.addEventListener("hashchange", rotear);
  if (!SJP.st.token) return telaLogin();
  try { SJP.st.user = await SJP.get("/api/v1/auth/eu"); } catch (e) { return telaLogin(); }
  const p = SJP.st.user.perfis;
  if (p.length === 1 && p[0] === "executor") { location.href = "/m/"; return; }     // executor trabalha no celular
  ESTR = await SJP.get("/api/v1/cadastros/estrutura");
  layout();
  es = SJP.stream(onNotif);
  atualizarSino();
  rotear();
}

function telaLogin(msg = "") {
  const demos = [["gestor", "Gestora (TI)"], ["atendente1", "Atendente"], ["dem1", "Demandante"], ["admin", "Admin"], ["exec3", "Executor → app"]];
  $("#app").innerHTML = `<div class="login card pop"><h1>🎯 Missão <b style="color:var(--cian)">SJP</b></h1>
    <p class="mut">Cada chamado é uma missão. Entre para acompanhar, organizar e reconhecer o trabalho da cidade.</p>
    <form id="fl"><label for="l">Usuário</label><input id="l" autocomplete="username" required>
    <label for="s">Senha</label><input id="s" type="password" autocomplete="current-password" required>
    <p class="erro" role="alert">${esc(msg)}</p><button class="grande" type="submit">Entrar</button></form>
    <p class="peq mut" style="margin-top:1rem">Ambiente de demonstração · senha de todos os usuários fictícios: <code>demo123</code></p>
    <div class="demo-chips">${demos.map(([l, n]) => `<button type="button" class="sec" data-l="${l}">${n}</button>`).join("")}</div></div>`;
  const entrar = async (l, s) => { try { await SJP.login(l, s); location.hash = ""; location.reload(); } catch (e) { telaLogin(e.message); } };
  $("#fl").onsubmit = e => { e.preventDefault(); entrar($("#l").value.trim(), $("#s").value); };
  $$("[data-l]").forEach(b => b.onclick = () => entrar(b.dataset.l, "demo123"));
}

function menuItens() {
  const m = [];
  if (SJP.tem("gestor")) m.push(["painel", "📊 Painel"]);
  if (SJP.tem("gestor", "atendente")) m.push(["tarefas", "📋 Tarefas"], ["nova", "➕ Nova tarefa"]);
  if (SJP.tem("demandante") && !SJP.tem("gestor", "atendente")) m.push(["minhas", "🙋 Minhas solicitações"]);
  m.push(["gamificacao", "🏆 Gamificação"]);
  if (SJP.tem("gestor")) m.push(["indicadores", "📈 Indicadores"], ["ia", "🤖 IA"], ["integracao", "🔌 Integração"], ["cadastros", "⚙️ Configuração"]);
  return m;
}

function layout() {
  const u = SJP.st.user;
  $("#app").innerHTML = `<header class="topo"><div class="logo">🎯 Missão <b>SJP</b></div><span class="mut peq">Prefeitura de São José dos Pinhais · SIMOT</span><span class="sp"></span>
    <a href="/m/" class="peq">📱 App do executor</a>
    <button class="sec bell" id="bSino" aria-label="Notificações">🔔<i id="nSino" hidden>0</i></button>
    <button class="sec" onclick="SJP.fonte()" aria-label="Aumentar ou reduzir tamanho da fonte">A+</button>
    <span title="${esc(u.perfis.join(", "))}">${esc(u.avatar)} ${esc(u.nome)}</span>
    <button class="sec" id="bSair">Sair</button></header>
    <nav class="menu" aria-label="Principal">${menuItens().map(([k, n]) => `<a href="#/${k}" data-k="${k}">${n}</a>`).join("")}</nav>
    <main id="principal" tabindex="-1"></main>`;
  $("#bSair").onclick = () => { SJP.sair(); location.hash = ""; location.reload(); };
  $("#bSino").onclick = abrirSino;
}

async function atualizarSino() {
  try { const n = await SJP.get("/api/v1/notificacoes"); naoLidas = n.nao_lidas; } catch (e) {}
  const el = $("#nSino"); if (el) { el.textContent = naoLidas; el.hidden = !naoLidas; }
}
async function abrirSino() {
  const n = await SJP.get("/api/v1/notificacoes");
  modal("Notificações", n.itens.length ? `<ul style="padding:0;margin:0">${n.itens.map(i => `<li style="list-style:none;padding:.5rem 0;border-bottom:1px solid var(--bd)">
    <b>${i.lida ? "" : "🔵 "}${esc(i.titulo)}</b><br><span class="mut peq">${esc(i.corpo)} · ${fdt(i.em)}</span>
    ${i.tarefa_id ? `<br><a href="#/tarefa/${i.tarefa_id}" onclick="document.querySelector('#modal').close()">abrir #${i.tarefa_id}</a>` : ""}</li>`).join("")}</ul>` : "<p>Nada por aqui.</p>");
  await SJP.post("/api/v1/notificacoes/lidas"); atualizarSino();
}
function onNotif(n) {
  toast(`${n.titulo} — ${n.corpo}`); atualizarSino();
  clearTimeout(timer); timer = setTimeout(() => { if (!$("#modal").open && !document.activeElement?.closest("form")) rotear(true); }, 600);
}

// ------------------------------------------------------------------ roteador
async function rotear(silencioso) {
  if (!SJP.st.user || !$("#principal")) return;
  const [, rota, arg] = (location.hash || "").split("/");
  const padrao = SJP.tem("gestor") ? "painel" : SJP.tem("atendente") ? "tarefas" : SJP.tem("demandante") ? "minhas" : "gamificacao";
  const k = rota || padrao;
  $$("nav.menu a").forEach(a => a.removeAttribute("aria-current"));
  const link = $(`nav.menu a[data-k="${k === "tarefa" ? "tarefas" : k}"]`); if (link) link.setAttribute("aria-current", "page");
  const main = $("#principal");
  try {
    if (!silencioso) main.innerHTML = '<p class="mut">Carregando…</p>';
    const html = await (V[k] || V.naoEncontrada)(arg);
    main.innerHTML = html.html ?? html;
    if (html.depois) html.depois();
    if (!silencioso) main.focus({ preventScroll: true });
  } catch (e) { main.innerHTML = `<div class="alerta erro" role="alert">${esc(e.message)}</div>`; }
}
V.naoEncontrada = () => "<p>Página não encontrada.</p>";

// ------------------------------------------------------------------ cartão de tarefa
function cartao(t) {
  return `<a class="tk" href="#/tarefa/${t.id}"><div class="t">#${t.id} · ${esc(t.titulo)}</div>
    <div class="m">${esc(t.unidade || t.local || "")}</div>
    <div class="m">${t.executor ? "👤 " + esc(t.executor) : "sem executor"} ${t.executores.length > 1 ? `+${t.executores.length - 1}` : ""}</div>
    <div style="margin-top:.3rem">${t.prioridade !== "normal" ? `<span class="badge p-${t.prioridade}">${SJP.PRIO[t.prioridade]}</span>` : ""}
    ${t.origem ? `<span class="badge leg" title="Registro de origem">${esc(t.origem.sistema)} #${esc(t.origem.id)} → ${esc(t.status_legado)}</span>` : ""}
    ${t.ia_pendente ? '<span class="badge ia">🤖 sugestão IA</span>' : ""}${t.reaberturas ? `<span class="badge">↩ ${t.reaberturas}×</span>` : ""}</div></a>`;
}

// ------------------------------------------------------------------ painel do gestor
V.painel = async () => {
  const [ts, ind] = await Promise.all([SJP.get("/api/v1/tarefas?limite=300"), SJP.get("/api/v1/indicadores?dias=120")]);
  const por = {}; ts.forEach(t => (por[t.status] ||= []).push(t));
  const ix = id => ind.indicadores.find(i => i.id === id);
  const cols = [["Para organizar", ["NOVA", "PENDENTE"], "🆕"], ["Atribuídas", ["ATRIBUIDA"], "🎯"], ["Em andamento", ["EM_ANDAMENTO"], "▶️"],
                ["Bloqueadas", ["BLOQUEADA"], "⛔"], ["Aguardando confirmação", ["CONCLUIDA_EXECUTOR"], "⏳"], ["Resolvidas", ["RESOLVIDA"], "🏆"]];
  const atencao = [...(por.BLOQUEADA || []), ...(por.PENDENTE || [])];
  return `<h1>Painel de missões</h1>
  <div class="grid g3" role="list">
    <div class="card kpi" role="listitem"><b>${ts.length}</b><span>missões na janela de 120 dias</span></div>
    <div class="card kpi" role="listitem"><b>${dur(ix("tempo_inicio").mediana)}</b><span>mediana até iniciar o atendimento</span></div>
    <div class="card kpi" role="listitem"><b>${ix("satisfacao").media ?? "—"}</b><span>satisfação média dos demandantes (1–5)</span></div>
    <div class="card kpi" role="listitem"><b>${(por.BLOQUEADA || []).length}</b><span>missões bloqueadas agora</span></div></div>
  ${atencao.length ? `<div class="alerta erro" style="margin-top:1rem" role="alert"><b>⚠️ Atenção da gestão:</b> ${atencao.map(t => `<a href="#/tarefa/${t.id}">#${t.id} ${chip(t.status)}</a>`).join(" · ")}</div>` : ""}
  <h2 style="margin-top:1.2rem">Quadro</h2>
  <div class="kanban">${cols.map(([n, sts, ic]) => {
    const itens = sts.flatMap(s => por[s] || []).slice(0, n === "Resolvidas" ? 6 : 30);
    return `<section class="col" aria-label="${n}"><h3><span>${ic} ${n}</span><span class="badge">${sts.flatMap(s => por[s] || []).length}</span></h3>${itens.map(cartao).join("") || '<p class="mut peq">—</p>'}</section>`; }).join("")}</div>`;
};

// ------------------------------------------------------------------ lista de tarefas
V.tarefas = async () => {
  const ts = await SJP.get("/api/v1/tarefas?limite=300");
  return { html: `<h1>Tarefas</h1><div class="row"><label class="sr" for="fq">Buscar</label><input id="fq" placeholder="Buscar por título, local, nº do chamado de origem…" style="max-width:420px">
    <label class="sr" for="fs">Situação</label><select id="fs" style="max-width:240px"><option value="">Todas as situações</option>${Object.entries(SJP.STATUS).map(([k, [i, t]]) => `<option value="${k}">${i} ${t}</option>`).join("")}</select></div>
    <div class="card" style="margin-top:.8rem;overflow:auto"><table><thead><tr><th>Nº</th><th>Tarefa</th><th>Situação</th><th>Equipe / executor</th><th>Prioridade</th><th>Origem</th><th>Aberta</th></tr></thead><tbody id="tb"></tbody></table></div>`,
    depois() {
      const pintar = () => {
        const q = $("#fq").value.toLowerCase(), s = $("#fs").value;
        $("#tb").innerHTML = ts.filter(t => (!s || t.status === s) && (!q || `${t.titulo} ${t.local} ${t.unidade} ${t.origem?.id || ""} ${t.id}`.toLowerCase().includes(q)))
          .map(t => `<tr><td><a href="#/tarefa/${t.id}">#${t.id}</a></td><td>${esc(t.titulo)}<br><span class="mut peq">${esc(t.unidade || t.local)}</span></td><td>${chip(t.status)}</td>
          <td>${esc(t.equipe || "—")}<br><span class="mut peq">${esc(t.executor || "sem executor")}</span></td><td class="p-${t.prioridade}">${SJP.PRIO[t.prioridade]}</td>
          <td>${t.origem ? `${esc(t.origem.sistema)} #${esc(t.origem.id)}<br><span class="mut peq">legado: ${esc(t.status_legado)}</span>` : '<span class="mut">plataforma</span>'}</td><td>${fdt(t.criado_em)}</td></tr>`).join("")
          || '<tr><td colspan="7" class="mut">Nenhuma tarefa.</td></tr>';
      };
      $("#fq").oninput = pintar; $("#fs").onchange = pintar; pintar();
    } };
};

V.minhas = async () => {
  const ts = await SJP.get("/api/v1/tarefas");
  return `<h1>Minhas solicitações</h1><p class="mut">Você acompanha o atendimento e confirma se o problema foi resolvido. Quem abre o chamado é sempre o atendente.</p>
  <div class="grid g2">${ts.map(cartao).join("") || "<p>Nenhuma solicitação.</p>"}</div>`;
};

// ------------------------------------------------------------------ detalhe da tarefa
const EVT = { criada: "🆕", atribuida: "🎯", iniciada: "▶️", andamento: "📝", impedimento: "⛔", impedimento_resolvido: "✅", apoio_solicitado: "🤝", concluida: "🏁", validada: "🏆", pendencia: "↩️", cancelada: "✖️", ia_conferida: "🤖" };
V.tarefa = async id => {
  const [t, ex] = await Promise.all([SJP.get(`/api/v1/tarefas/${id}`), SJP.tem("gestor") ? SJP.get("/api/v1/cadastros/usuarios?perfil=executor") : []]);
  const a = t.acoes, ia = t.ia_sugestao;
  const classe = e => ({ impedimento: "imp", validada: "val", pendencia: "pen", ia_conferida: "ia" }[e.tipo] || "");
  const html = `<p><a href="#/${SJP.tem("gestor", "atendente") ? "tarefas" : "minhas"}">← voltar</a></p>
  <div class="detalhe"><div>
   <div class="card"><div class="row"><h1 style="margin:0">#${t.id} · ${esc(t.titulo)}</h1><span class="sp"></span>${chip(t.status)}</div>
    <p>${esc(t.descricao) || '<span class="mut">sem descrição</span>'}</p>
    <div class="grid g2 peq"><div>📍 <b>Local:</b> ${esc(t.local || "—")}<br>🏢 <b>Unidade:</b> ${esc(t.unidade || "—")}<br>👤 <b>Solicitante:</b> ${esc(t.solicitante || "—")} ${esc(t.solicitante_contato)}</div>
     <div>🧩 <b>Tipo:</b> ${esc(t.tipo || "—")}<br>👥 <b>Equipe:</b> ${esc(t.equipe || "—")}<br>⚙️ <b>Complexidade:</b> ${esc(t.complexidade)} · <span class="p-${t.prioridade}">${SJP.PRIO[t.prioridade]}</span></div></div>
    ${t.origem ? `<div class="alerta" style="border-color:var(--amb)"><b>🔌 Registro de origem:</b> ${esc(t.origem.nome)} — chamado <b>#${esc(t.origem.id)}</b>. Status espelhado no legado: <b>${esc(t.status_legado)}</b></div>` : '<p class="peq mut">Cadastrada diretamente na plataforma (setor sem sistema próprio).</p>'}
    <p>${t.executores.map(e => `<span class="badge">${e.avatar} ${esc(e.nome)} · ${e.papel === "principal" ? "responsável" : "apoio"}</span>`).join("") || '<span class="mut">sem executor</span>'}</p>
    <div class="row">${a.includes("atribuir") ? '<button id="bAtr">🎯 Atribuir missão</button>' : ""}${a.includes("resolver_impedimento") ? '<button class="ok" id="bImp">✅ Tratar impedimento</button>' : ""}
     ${a.includes("cancelar") ? '<button class="sec perigo" id="bCan">Cancelar</button>' : ""}<button class="sec viol" id="bRes">🤖 Resumo da execução (IA)</button></div>
    <div id="resumo"></div></div>
   ${t.link_validacao ? `<div class="card" style="margin-top:1rem"><h3>⏳ Aguardando a confirmação do demandante</h3><p class="peq mut">Em produção o link vai por SMS/WhatsApp institucional/e-mail, ou o atendente confirma por telefone. Uso único.</p>
     <div class="row"><input readonly value="${esc(t.link_validacao)}" id="lnk" aria-label="Link de validação"><button class="sec" id="bCopia">Copiar</button><a href="${esc(t.link_validacao)}" target="_blank" rel="noopener">abrir como demandante ↗</a></div></div>` : ""}
   ${a.includes("validar") ? validarForm(t) : ""}
   <div class="card" style="margin-top:1rem"><h2>Linha do tempo (trilha de auditoria)</h2><ol class="tl" style="padding-left:1rem">${t.eventos.map(e => `<li class="${classe(e)}"><b>${EVT[e.tipo] || "•"} ${esc(e.ator)}</b> <span class="mut peq">${fdt(e.criado_em)}</span><br>${esc(e.texto)}
     ${e.dados?.lat ? `<br><span class="peq mut">📍 ${e.dados.lat.toFixed(4)}, ${e.dados.lon.toFixed(4)}</span>` : ""}
     ${e.evidencias.map(v => `<a href="#" data-ev="${v.url}" data-mime="${esc(v.mime)}" data-nome="${esc(v.nome)}">📎 ${esc(v.nome)}</a>`).join(" ")}</li>`).join("")}</ol></div></div>
   <aside>${iaPainel(t, a)}${t.impedimentos.length ? `<div class="card" style="margin-top:1rem"><h3>⛔ Impedimentos</h3>${t.impedimentos.map(i => `<p class="peq"><b>${SJP.IMP[i.tipo]}</b><br>${esc(i.descricao)}<br>${i.resolvido_em ? `<span class="okc">✔ ${esc(i.resolucao)}</span>` : '<span class="erro">em aberto</span>'}</p>`).join("")}${t.bloqueada_min ? `<p class="peq mut">Tempo bloqueada (SLA congelado): ${dur(t.bloqueada_min)}</p>` : ""}</div>` : ""}
   <div class="card" style="margin-top:1rem"><h3>⏱️ Tempos</h3><p class="peq">Aberta: ${fdt(t.criado_em)}<br>Atribuída: ${fdt(t.atribuido_em)}<br>Iniciada: ${fdt(t.iniciado_em)}<br>Concluída (executor): ${fdt(t.concluido_exec_em)}<br>Resolvida (demandante): ${fdt(t.resolvido_em)}<br>${t.avaliacao ? `Avaliação: ${"★".repeat(t.avaliacao)}${"☆".repeat(5 - t.avaliacao)} ${esc(t.comentario_avaliacao)}` : ""}</p></div></aside></div>`;
  return { html, depois() {
    $("#bAtr")?.addEventListener("click", () => atribuirModal(t, ex));
    $("#bImp")?.addEventListener("click", () => impedimentoModal(t, ex));
    $("#bCan")?.addEventListener("click", () => modal("Cancelar tarefa", '<label for="mt">Motivo</label><textarea id="mt" name="motivo" required minlength="3"></textarea>', "Cancelar tarefa", async f => { await SJP.post(`/api/v1/tarefas/${t.id}/cancelar`, { motivo: f.get("motivo") }); rotear(); }));
    $("#bRes")?.addEventListener("click", async () => { const r = await SJP.get(`/api/v1/tarefas/${t.id}/ia/resumo`); $("#resumo").innerHTML = `<div class="ia-box" style="margin-top:.8rem"><h3>🤖 Resumo <span class="tag-sim">${esc(r.modo)}</span></h3><p>${esc(r.resumo)}</p></div>`; });
    $("#bCopia")?.addEventListener("click", () => { navigator.clipboard?.writeText($("#lnk").value); toast("Link copiado"); });
    $("#iaOk")?.addEventListener("click", () => decidirIA(t, true)); $("#iaNo")?.addEventListener("click", () => decidirIA(t, false));
    $$("[data-ev]").forEach(a => a.onclick = async e => { e.preventDefault(); await verEvidencia(a); });
    bindValidar(t);
  } };
};

async function verEvidencia(a) {
  const r = await fetch(a.dataset.ev, { headers: { Authorization: "Bearer " + SJP.st.token } });
  if (!r.ok) return toast("Arquivo indisponível");
  const url = URL.createObjectURL(await r.blob());
  if ((a.dataset.mime || "").startsWith("image/")) modal(a.dataset.nome, `<img src="${url}" alt="Evidência: ${esc(a.dataset.nome)}" style="max-width:100%;border-radius:10px">`);
  else window.open(url, "_blank");
}

function iaPainel(t, a) {
  const ia = t.ia_sugestao; if (!ia) return "";
  const c = ia.classificacao || [];
  return `<div class="ia-box"><h3>🤖 Sugestão da IA <span class="tag-real">modelo local</span></h3>
    <p class="peq mut">${esc(ia.aviso)} Estado: <b>${ia.estado}</b>${ia.conferido_por ? " por " + esc(ia.conferido_por) : ""}</p>
    ${c.map((x, i) => `<div class="peq"><b>${i === 0 ? "▸ " : ""}${esc(x.rotulo)}</b> → ${esc(x.equipe)} <span class="mut">(${Math.round(x.confianca * 100)}%)</span>
      <div class="barra" aria-hidden="true"><i style="width:${x.confianca * 100}%"></i></div>${i === 0 && x.palavras?.length ? `<span class="mut">pesaram: ${x.palavras.map(esc).join(", ")}</span>` : ""}</div>`).join("")}
    <p class="peq" style="margin-top:.6rem">Prioridade sugerida: <b>${SJP.PRIO[ia.prioridade.valor]}</b><br><span class="mut">${ia.prioridade.motivos.map(esc).join("; ")}</span></p>
    ${ia.lacunas?.length ? `<div class="alerta peq"><b>Informações que podem faltar:</b><ul style="margin:.3rem 0 0;padding-left:1.1rem">${ia.lacunas.map(l => `<li>${esc(l.pergunta)}</li>`).join("")}</ul></div>` : '<p class="peq okc">✔ Nenhuma lacuna evidente.</p>'}
    ${a.includes("conferir_ia") ? '<div class="row"><button class="viol" id="iaOk">Aceitar sugestão</button><button class="sec" id="iaNo">Rejeitar</button></div>' : ""}</div>`;
}
async function decidirIA(t, aceitar) { await SJP.post(`/api/v1/tarefas/${t.id}/ia/decidir`, { aceitar }); toast(aceitar ? "Sugestão aplicada e registrada." : "Sugestão rejeitada e registrada."); rotear(); }

async function atribuirModal(t, ex) {
  const abertas = await SJP.get("/api/v1/tarefas?status=ATRIBUIDA,EM_ANDAMENTO,BLOQUEADA&limite=500");
  const carga = {}; abertas.forEach(x => x.executores.forEach(e => carga[e.id] = (carga[e.id] || 0) + 1));
  const atuais = t.executores.map(e => e.id);
  const ordem = [...ex].sort((a, b) => (b.equipe_id === t.equipe_id) - (a.equipe_id === t.equipe_id) || (carga[a.id] || 0) - (carga[b.id] || 0));
  modal("Atribuir missão #" + t.id, `<p class="peq mut">Escolha o responsável (1º) e, se quiser, colegas de apoio. Executores da equipe <b>${esc(t.equipe || "—")}</b> aparecem primeiro, com a carga atual.</p>
    <label for="resp">Responsável</label><select id="resp" name="resp" required>${ordem.map(u => `<option value="${u.id}" ${atuais[0] === u.id ? "selected" : ""}>${u.avatar} ${esc(u.nome)} — ${esc(u.equipe || "")} · ${carga[u.id] || 0} em aberto</option>`).join("")}</select>
    <fieldset style="border:1px solid var(--bd);border-radius:10px;margin-top:.7rem"><legend>Apoio (opcional)</legend>${ordem.map(u => `<label style="font-weight:400;display:flex;gap:.5rem;align-items:center"><input type="checkbox" name="ap" value="${u.id}" style="width:auto;min-height:0" ${atuais.slice(1).includes(u.id) ? "checked" : ""}> ${u.avatar} ${esc(u.nome)} <span class="mut peq">${esc(u.equipe || "")}</span></label>`).join("")}</fieldset>
    <label for="pr">Prioridade</label><select id="pr" name="pr">${Object.entries(SJP.PRIO).map(([k, v]) => `<option value="${k}" ${t.prioridade === k ? "selected" : ""}>${v}</option>`).join("")}</select>
    <label for="ob">Observação para o executor</label><textarea id="ob" name="ob"></textarea>`, "Enviar missão 🎯", async f => {
    const ids = [Number(f.get("resp")), ...f.getAll("ap").map(Number).filter(i => i !== Number(f.get("resp")))];
    await SJP.post(`/api/v1/tarefas/${t.id}/atribuir`, { executor_ids: ids, observacao: f.get("ob"), prioridade: f.get("pr") }); toast("Missão enviada ao executor."); rotear();
  });
}
function impedimentoModal(t, ex) {
  const imp = t.impedimentos.filter(i => !i.resolvido_em).pop();
  const sug = [...t.eventos].reverse().find(e => e.tipo === "impedimento")?.dados?.ia_apoio;
  modal("Tratar impedimento", `<div class="alerta"><b>${SJP.IMP[imp?.tipo] || "Impedimento"}</b><br>${esc(imp?.descricao || "")}</div>
    ${sug ? `<div class="ia-box peq"><b>🤖 Sugestão:</b> acionar a equipe <b>${esc(sug.equipe)}</b> — ${esc(sug.motivo)}.</div>` : ""}
    <label for="rs">Providência tomada</label><textarea id="rs" name="rs" required minlength="3"></textarea>
    <fieldset style="border:1px solid var(--bd);border-radius:10px;margin-top:.7rem"><legend>Adicionar apoio (opcional)</legend>${ex.filter(u => !t.executores.some(e => e.id === u.id)).map(u => `<label style="font-weight:400;display:flex;gap:.5rem;align-items:center"><input type="checkbox" name="ap" value="${u.id}" style="width:auto;min-height:0"> ${u.avatar} ${esc(u.nome)} <span class="mut peq">${esc(u.equipe || "")}</span></label>`).join("")}</fieldset>`,
    "Liberar a missão ✅", async f => { await SJP.post(`/api/v1/tarefas/${t.id}/impedimento/resolver`, { resolucao: f.get("rs"), apoio_ids: f.getAll("ap").map(Number) }); toast("Missão liberada para continuar."); rotear(); });
}

// ------------------------------------------------------------------ validação (demandante autenticado)
function validarForm(t) {
  return `<div class="card pop" style="margin-top:1rem;border-color:var(--ok)"><h2>O problema foi resolvido?</h2>
   <p class="peq mut">O executor informou a conclusão. Só você confirma se a necessidade foi atendida.</p>
   <div class="row"><button class="ok" id="vSim">✅ Sim, foi resolvido</button><button class="sec perigo" id="vNao">↩ Não resolveu</button></div><div id="vCampos"></div></div>`;
}
function bindValidar(t) {
  $("#vSim")?.addEventListener("click", () => { $("#vCampos").innerHTML = `<fieldset class="estrelas" style="border:0;padding:0;margin:.8rem 0"><legend>Nota do atendimento</legend>${[1, 2, 3, 4, 5].map(n => `<label><input type="radio" name="n" value="${n}" required><span aria-hidden="true">★</span><span class="sr">${n}</span></label>`).join("")}</fieldset>
    <label for="vc">Comentário (opcional)</label><textarea id="vc"></textarea><button class="ok" id="vEnv">Enviar confirmação</button>`;
    $("#vEnv").onclick = async () => { const n = $('input[name="n"]:checked'); if (!n) return toast("Escolha uma nota de 1 a 5"); await SJP.post(`/api/v1/tarefas/${t.id}/validar`, { resolvido: true, nota: Number(n.value), comentario: $("#vc").value }); toast("Obrigado!"); rotear(); }; });
  $("#vNao")?.addEventListener("click", () => { $("#vCampos").innerHTML = `<label for="vm">O que ainda não foi resolvido?</label><textarea id="vm" required></textarea><button class="perigo" id="vEnv">Informar pendência</button>`;
    $("#vEnv").onclick = async () => { try { await SJP.post(`/api/v1/tarefas/${t.id}/validar`, { resolvido: false, motivo_pendencia: $("#vm").value }); toast("Pendência registrada: a tarefa voltou ao fluxo."); rotear(); } catch (e) { toast(e.message); } }; });
}

// ------------------------------------------------------------------ nova tarefa (atendente)
V.nova = async () => {
  const dem = await SJP.get("/api/v1/cadastros/usuarios?perfil=demandante");
  const u = SJP.st.user; const setorPadrao = u.setor_id || ESTR.setores[0].id;
  return { html: `<h1>Nova tarefa</h1><p class="mut">Cadastro feito pelo <b>atendente</b>, a partir da ligação do demandante — para setores sem sistema próprio. (Setores com legado recebem as tarefas pela integração.)</p>
   <div class="detalhe"><form class="card" id="fn"><label for="ti">Título</label><input id="ti" required minlength="3" placeholder="Ex.: Ponto de rede não funciona">
    <label for="de">Descrição do problema</label><textarea id="de" placeholder="O que aconteceu, desde quando, o que já foi tentado…"></textarea>
    <div class="grid g2"><div><label for="un">Unidade / departamento</label><input id="un"></div><div><label for="lo">Local (sala, andar, endereço)</label><input id="lo"></div>
    <div><label for="sn">Solicitante</label><select id="sn"><option value="">— informar manualmente / sem cadastro —</option>${dem.map(d => `<option value="${d.id}" data-n="${esc(d.nome)}" data-c="${esc(d.contato)}">${esc(d.nome)}</option>`).join("")}</select></div>
    <div><label for="sc">Ramal / telefone</label><input id="sc"></div>
    <div><label for="se">Setor responsável</label><select id="se">${ESTR.setores.map(s => `<option value="${s.id}" ${s.id === setorPadrao ? "selected" : ""}>${esc(s.nome)}</option>`).join("")}</select></div>
    <div><label for="tp">Tipo de tarefa (fluxo)</label><select id="tp"></select></div>
    <div><label for="eq">Equipe</label><select id="eq"></select></div>
    <div><label for="pr">Prioridade</label><select id="pr">${Object.entries(SJP.PRIO).map(([k, v]) => `<option value="${k}" ${k === "normal" ? "selected" : ""}>${v}</option>`).join("")}</select></div></div>
    <p class="erro" id="er" role="alert"></p><button class="grande" type="submit" style="margin-top:.8rem">Registrar tarefa</button></form>
   <aside><div class="ia-box" id="iaPrev"><h3>🤖 Assistente do atendente</h3><p class="peq mut">Conforme você descreve, a IA local sugere equipe, prioridade e perguntas para completar o chamado. Você decide.</p></div></aside></div>`,
  depois() {
    const f = id => $("#" + id);
    const popTipos = () => { const sid = Number(f("se").value);
      f("tp").innerHTML = '<option value="">—</option>' + ESTR.tipos.filter(t => t.setor_id === sid && t.ativo).map(t => `<option value="${t.id}">${esc(t.nome)}</option>`).join("");
      f("eq").innerHTML = '<option value="">— definir depois —</option>' + ESTR.equipes.filter(e => e.setor_id === sid).map(e => `<option value="${e.id}">${esc(e.nome)}</option>`).join(""); };
    f("se").onchange = popTipos; popTipos();
    f("tp").onchange = () => { const t = ESTR.tipos.find(x => x.id === Number(f("tp").value)); if (t?.equipe_padrao_id) f("eq").value = t.equipe_padrao_id; };
    f("sn").onchange = () => { const o = f("sn").selectedOptions[0]; if (o?.dataset.c && !f("un").value) f("un").value = o.dataset.c; };
    let to; const analisar = () => { clearTimeout(to); to = setTimeout(async () => {
      if ((f("ti").value + f("de").value).trim().length < 8) return;
      const r = await SJP.post("/api/v1/ia/analisar", { titulo: f("ti").value, descricao: f("de").value, unidade_demandante: f("un").value, local: f("lo").value, solicitante_contato: f("sc").value });
      $("#iaPrev").innerHTML = `<h3>🤖 Assistente do atendente</h3>${r.classificacao.map((c, i) => `<button type="button" class="${i ? "sec" : "viol"}" style="margin:.2rem 0;width:100%;text-align:left" data-c='${JSON.stringify({ e: c.equipe_id, t: c.tipo_id, s: c.setor_id })}'>${i === 0 ? "★ " : ""}${esc(c.rotulo)} → ${esc(c.equipe)} · ${Math.round(c.confianca * 100)}%</button>`).join("")}
        <p class="peq">Prioridade sugerida: <b>${SJP.PRIO[r.prioridade.valor]}</b> <button type="button" class="sec" style="min-height:32px;padding:.1rem .6rem" id="aplP">usar</button><br><span class="mut">${r.prioridade.motivos.map(esc).join("; ")}</span></p>
        ${r.lacunas.length ? `<div class="alerta peq"><b>Pergunte ao solicitante:</b><ul style="margin:.3rem 0 0;padding-left:1.1rem">${r.lacunas.map(l => `<li>${esc(l.pergunta)}</li>`).join("")}</ul></div>` : '<p class="peq okc">✔ Chamado completo.</p>'}`;
      $$("#iaPrev [data-c]").forEach(b => b.onclick = () => { const c = JSON.parse(b.dataset.c); if (c.s) { f("se").value = c.s; popTipos(); } if (c.t) f("tp").value = c.t; if (c.e) f("eq").value = c.e; toast("Sugestão aplicada (você pode alterar)."); });
      $("#aplP")?.addEventListener("click", () => { f("pr").value = r.prioridade.valor; });
    }, 450); };
    ["ti", "de", "un", "lo", "sc"].forEach(i => f(i).addEventListener("input", analisar));
    f("fn").onsubmit = async e => { e.preventDefault(); f("er").textContent = "";
      const o = f("sn").selectedOptions[0];
      try { const t = await SJP.post("/api/v1/tarefas", { titulo: f("ti").value, descricao: f("de").value, setor_id: Number(f("se").value), tipo_id: f("tp").value ? Number(f("tp").value) : null,
        equipe_id: f("eq").value ? Number(f("eq").value) : null, local: f("lo").value, unidade_demandante: f("un").value, solicitante_nome: o?.dataset.n || "", solicitante_contato: f("sc").value,
        demandante_id: f("sn").value ? Number(f("sn").value) : null, prioridade: f("pr").value }); toast("Tarefa registrada ✔"); location.hash = "#/tarefa/" + t.id;
      } catch (err) { f("er").textContent = err.message; } };
  } };
};
