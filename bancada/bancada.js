/* Bancada — tela guiada que usa a API REAL do protótipo. Sem dependências externas. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = (n, d = 1) => Number(n ?? 0).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const cut = (s, n) => (s || "").length > n ? s.slice(0, n - 1) + "…" : (s || "");
const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");

/* ---------------------------------------------------------------- API (vários perfis em segundo plano) */
const tokens = {}, users = {};
async function fazerLogin(l) {
  if (tokens[l]) return;
  const r = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login: l, senha: "demo123" }) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail || "Falha ao entrar como " + l);
  tokens[l] = j.token; users[l] = j.usuario;
}
async function api(as, method, path, body, tentou) {
  await fazerLogin(as);
  const h = { Authorization: "Bearer " + tokens[as] };
  let b;
  if (body instanceof FormData) b = body; else if (body !== undefined) { h["Content-Type"] = "application/json"; b = JSON.stringify(body); }
  let r;
  try { r = await fetch(path, { method, headers: h, body: b }); } catch (e) { throw new Error("Sem conexão com o servidor."); }
  if (r.status === 401 && !tentou) { delete tokens[as]; return api(as, method, path, body, true); }
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(typeof j?.detail === "string" ? j.detail : "Erro " + r.status);
  return j;
}

/* ---------------------------------------------------------------- estado da jornada */
let J = {}; try { J = JSON.parse(sessionStorage.getItem("bj") || "{}"); } catch (e) {}
const salvarJ = () => { try { sessionStorage.setItem("bj", JSON.stringify(J)); } catch (e) {} };
let msgs = [];                       // conversa do assistente (apenas na página)
let fase = 0;                        // 0 registro … 5 tudo concluído
let tarefa = null;

async function atualizarFase() {
  fase = 0; tarefa = null;
  if (!J.os) return;
  try { tarefa = await api("gestor", "GET", "/api/v1/tarefas/" + J.os); } catch (e) { J.os = null; salvarJ(); return; }
  const s = tarefa.status;
  if (s === "NOVA") fase = tarefa.ia_sugestao?.estado === "pendente" ? 1 : 2;
  else if (s === "ATRIBUIDA" || s === "PENDENTE") fase = 3;
  else if (s === "EM_ANDAMENTO" || s === "BLOQUEADA") fase = 4;
  else fase = 5;
}
const ROT_FASES = ["Registro", "Triagem", "Despacho", "Aceite", "Conclusão"];
const trilha = () => `<div class="passos" aria-label="Progresso da jornada">${ROT_FASES.map((n, i) =>
  `<span class="${i < fase ? "ok" : i === fase ? "agora" : ""}"><i></i>${n}</span>`).join("")}</div>`;
const cab = (etapa, titulo, extra = "") => `<div class="cab"><div><div class="eyebrow">${etapa}</div><h1>${titulo}</h1>${extra}</div>${J.os ? trilha() : ""}</div>`;
const kpi = (rot, val, ico, cls = "", nota = "") => `<div class="card kpi"><div class="rot">${rot}</div><div class="ico" aria-hidden="true">${ico}</div><div class="val ${cls}">${val}</div>${nota ? `<div class="nota">${nota}</div>` : ""}</div>`;
function toast(m) { document.querySelectorAll(".toast").forEach(t => t.remove()); const t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); t.textContent = m; document.body.appendChild(t); setTimeout(() => t.remove(), 3200); }
const erro = e => `<div class="aviso" role="alert">⚠️ <span>${esc(e.message || e)}</span></div>`;

/* ---------------------------------------------------------------- abas */
const ABAS = [["geral", "🏠", "Início"], ["entrada", "📥", "Entrada"], ["triagem", "🧭", "Triagem"], ["despacho", "🗺️", "Despacho"],
  ["tecnico", "📱", "Técnico"], ["resultado", "📊", "Resultado"], ["assistente", "💬", "Assistente"]];
const VIEWS = {};
function montarAbas(atual) {
  $("#abas").innerHTML = ABAS.map(([id, ico, nome]) => `<button data-aba="${id}" ${id === atual ? 'aria-current="page"' : ""}>${ico} ${nome}</button>`).join("");
  document.querySelectorAll("[data-aba]").forEach(b => b.onclick = () => { location.hash = "#/" + b.dataset.aba; });
}
async function rotear() {
  const id = (location.hash.replace("#/", "") || "geral");
  const aba = ABAS.find(a => a[0] === id) ? id : "geral";
  montarAbas(aba);
  const el = $("#tela");
  el.innerHTML = '<div class="carregando">Carregando…</div>';
  try { await atualizarFase(); el.innerHTML = await VIEWS[aba](); const pos = VIEWS[aba + "_pos"]; if (pos) await pos(); }
  catch (e) { el.innerHTML = cab("Ops", "Algo não carregou") + erro(e); }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", rotear);
const ir = id => { location.hash = "#/" + id; };

/* ---------------------------------------------------------------- 1. Visão geral */
VIEWS.geral = async () => {
  const b = await api("gestor", "GET", "/api/v1/indicadores/baseline");
  const h = b.horas_ate_conclusao || {};
  const pilares = [
    ["🎯", "Rastreabilidade", "Cada OS responde: quando, como, quem, o que foi feito, há pendências, há fotos.", "Funcionando", "verde"],
    ["🧠", "IA que se alimenta", "O assistente aprende com cada OS concluída e passa a orientar o técnico.", "Funcionando", "verde"],
    ["🏅", "Pontos por dado entregue", "Quanto mais completa a OS, mais o técnico pontua. Dados melhores para todos.", "Parcial", "ambar"],
    ["🏛️", "O que o cidadão vê", "Indicadores agregados que o secretário pode mostrar, sem dado pessoal.", "Ideia", ""],
  ];
  return `
  <div class="cab"><div><div class="eyebrow">Protótipo funcional · Hackathon SJP</div>
    <h1>Cada chamado resolvido deixa o próximo mais rápido</h1>
    <p class="lead">Uma camada ao lado do sistema que a prefeitura já usa: dá visão ao gestor e apoio ao técnico em campo. Tudo nesta tela usa o sistema de verdade.</p></div></div>
  <div class="eyebrow" style="margin:0 0 8px">Por quê · diagnóstico real do Help Desk de TI (${esc(b.periodo)}, dados agregados)</div>
  <div class="grid4">
    ${kpi("Chamados analisados", nf(b.chamados, 0), "🗂️", "", "dados reais, sem nomes")}
    ${kpi("Mediana até concluir", nf(h.mediana) + " h", "⏱️", "azul")}
    ${kpi("Média até concluir", nf(h.media) + " h", "📈", "ambar", "puxada pelos casos parados")}
    ${kpi("Acima de 72 horas", nf(b.percentual_conclusao_acima_de_72h) + "%", "⚠️", "ambar", "dos chamados concluídos")}
  </div>
  <div class="eyebrow" style="margin:22px 0 8px">Como · quatro pilares ligados em ciclo</div>
  <div class="grid4">${pilares.map(([i, t, d, s, c]) => `<div class="card flat"><div style="font-size:26px">${i}</div><h3>${t}</h3><p class="mut peq" style="margin:4px 0 10px">${d}</p><span class="tag ${c}">${s}</span></div>`).join("")}</div>
  <div class="card" style="margin-top:14px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center">
    <div><h2>Siga as abas na ordem</h2><div class="mut">Registrar um chamado → confirmar a triagem da IA → despachar → ver no celular do técnico → resultado. A aba <b>Assistente</b> mostra a IA aprendendo.</div></div>
    <button class="btn" id="bComecar">Começar a jornada →</button></div>
  <p class="peq mut" style="margin-top:14px">Dados de demonstração fictícios. Economias de rota são estimativas. O diagnóstico acima é real e agregado.</p>`;
};
VIEWS.geral_pos = () => { $("#bComecar").onclick = () => ir("entrada"); };

/* ---------------------------------------------------------------- 2. Entrada */
const CENARIOS = [
  { titulo: "Computadores da recepção da UPA sem internet", descricao: "Desde as 7h os computadores da recepção estão sem conexão com a internet e o atendimento está parado.", local: "Recepção", unidade: "UPA Afonso Pena", contato: "ramal 2210" },
  { titulo: "Impressora da farmácia não imprime as receitas", descricao: "A impressora da farmácia liga mas não imprime; fila de pacientes aguardando.", local: "Farmácia", unidade: "US Padre Pedro Fuss - Veneza", contato: "ramal 3340" },
  { titulo: "Telefone sem tom na sala de vacinas", descricao: "O telefone da sala de vacinas está mudo, não recebe nem faz ligações.", local: "Sala de vacinas", unidade: "US Marilene Horning - Parque da Fonte", contato: "ramal 4120" },
];
VIEWS.entrada = async () => `
  ${cab("Etapa 1 · Atendimento", "Um chamado chega")}
  <div class="duas">
    <div class="card"><h2>Registrar chamado</h2><div class="mut peq">Como a atendente recebe o pedido. Escolha um exemplo ou escreva o seu.</div>
      <div class="chips" id="ex">${CENARIOS.map((c, i) => `<button class="chip-b" data-i="${i}">Exemplo ${i + 1}</button>`).join("")}</div>
      <label class="c" for="fT">O que aconteceu?</label><input class="in" id="fT">
      <label class="c" for="fD">Detalhes</label><textarea class="in" id="fD"></textarea>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div><label class="c" for="fU">Unidade</label><input class="in" id="fU"></div><div><label class="c" for="fL">Local / sala</label><input class="in" id="fL"></div></div>
      <label class="c" for="fC">Contato do solicitante</label><input class="in" id="fC">
      <div class="linha" style="margin-top:16px"><button class="btn" id="bReg">Registrar chamado</button>
        ${J.os ? `<button class="btn sec" id="bProx">Chamado #${J.os} já registrado · ir para a triagem →</button>` : ""}</div>
      <div id="regMsg" style="margin-top:12px"></div></div>
    <div class="card ia" id="iaPrev"><div class="sel">✨ Prévia da IA · sugere, não decide</div><div class="mut">Digite para ver a classificação, a prioridade e o que falta perguntar.</div></div>
  </div>`;
VIEWS.entrada_pos = () => {
  const campos = { t: $("#fT"), d: $("#fD"), u: $("#fU"), l: $("#fL"), c: $("#fC") };
  const preencher = i => { const c = CENARIOS[i]; campos.t.value = c.titulo; campos.d.value = c.descricao; campos.u.value = c.unidade; campos.l.value = c.local; campos.c.value = c.contato; previa(); };
  document.querySelectorAll("#ex .chip-b").forEach(b => b.onclick = () => preencher(+b.dataset.i));
  let tm; const agendar = () => { clearTimeout(tm); tm = setTimeout(previa, 450); };
  Object.values(campos).forEach(c => c.addEventListener("input", agendar));
  async function previa() {
    const box = $("#iaPrev"); if (!campos.t.value.trim()) return;
    try {
      const r = await api("atendente1", "POST", "/api/v1/ia/analisar", { titulo: campos.t.value, descricao: campos.d.value, unidade_demandante: campos.u.value, local: campos.l.value, solicitante_contato: campos.c.value });
      const top = (r.classificacao || []).slice(0, 3);
      box.innerHTML = `<div class="sel">✨ Prévia da IA · sugere, não decide</div>
        <h3>Categoria provável</h3>${top.map(c => `<div class="peq"><b>${esc(c.rotulo)}</b> · ${esc(c.equipe || "")} · ${Math.round(c.confianca * 100)}%</div><div class="barra"><i style="width:${Math.max(3, Math.round(c.confianca * 100))}%"></i></div>`).join("")}
        <h3 style="margin-top:8px">Prioridade</h3><div><span class="tag ${r.prioridade?.valor === "urgente" || r.prioridade?.valor === "alta" ? "verm" : "azul"}">${esc(r.prioridade?.valor || "normal")}</span> <span class="peq mut">${esc((r.prioridade?.motivos || []).join("; "))}</span></div>
        ${(r.lacunas || []).length ? `<h3 style="margin-top:12px">O que ainda falta perguntar</h3><ul class="lista">${r.lacunas.slice(0, 3).map(l => `<li>❓ <span>${esc(l.pergunta)}</span></li>`).join("")}</ul>` : `<div class="aviso ok" style="margin-top:12px">✅ Chamado completo: nada a perguntar.</div>`}
        ${(r.similares || []).length ? `<h3 style="margin-top:12px">Casos parecidos já resolvidos</h3><ul class="lista">${r.similares.map(s => `<li><span class="n">#${s.tarefa_id}</span><span><b>${esc(s.titulo)}</b><br><span class="peq mut">${esc(cut(s.solucao, 120))}</span></span></li>`).join("")}</ul>` : ""}`;
    } catch (e) { box.innerHTML = erro(e); }
  }
  preencher(0);
  if ($("#bProx")) $("#bProx").onclick = () => ir("triagem");
  $("#bReg").onclick = async () => {
    const b = $("#bReg"); b.disabled = true; $("#regMsg").innerHTML = "";
    try {
      const t = await api("atendente1", "POST", "/api/v1/tarefas", { titulo: campos.t.value, descricao: campos.d.value, setor_id: 1, local: campos.l.value,
        unidade_demandante: campos.u.value, solicitante_nome: "Servidor da unidade (fictício)", solicitante_contato: campos.c.value });
      J.os = t.id; salvarJ(); toast("Chamado #" + t.id + " registrado");
      ir("triagem");
    } catch (e) { $("#regMsg").innerHTML = erro(e); b.disabled = false; }
  };
};

/* ---------------------------------------------------------------- 3. Triagem */
async function garantirOS() {
  if (J.os) return true;
  const ts = await api("gestor", "GET", "/api/v1/tarefas?status=NOVA");
  const t = ts.find(x => x.ia_pendente) || ts[0];
  if (t) { J.os = t.id; salvarJ(); await atualizarFase(); return true; }
  return false;
}
VIEWS.triagem = async () => {
  if (!await garantirOS()) return cab("Etapa 2 · Triagem", "Confirmar a triagem da IA") + `<div class="card"><h2>Ainda não há chamado novo</h2><p class="mut">Registre um chamado na aba Entrada.</p><button class="btn" id="bIrE">Ir para a Entrada</button></div>`;
  const t = tarefa, s = t.ia_sugestao || {}, top = (s.classificacao || [])[0];
  const pend = s.estado === "pendente";
  return `${cab("Etapa 2 · Triagem humana", "A IA sugere, a pessoa decide")}
  <div class="duas">
    <div class="card"><div class="linha" style="justify-content:space-between"><h2>Chamado #${t.id}</h2><span class="tag ${t.status === "NOVA" ? "azul" : "verde"}">${esc(SJPStatus(t.status))}</span></div>
      <h3>${esc(t.titulo)}</h3><p class="mut" style="margin:4px 0 12px">${esc(t.descricao || "")}</p>
      <div class="linha peq mut"><span>📍 ${esc(t.unidade || t.local || "—")}</span><span>👤 ${esc(t.solicitante || "—")}</span></div>
      <h3 style="margin-top:16px">Campos hoje</h3>
      <div class="linha"><span class="tag">Equipe: ${esc(t.equipe || "—")}</span><span class="tag">Tipo: ${esc(t.tipo || "—")}</span><span class="tag">Prioridade: ${esc(t.prioridade)}</span></div></div>
    <div class="card ia"><div class="sel">✨ Sugestão da IA (local, sem nuvem)</div>
      ${top ? `<h2 style="font-size:20px">${esc(top.rotulo)}</h2><div class="peq mut">Equipe sugerida: <b>${esc(top.equipe)}</b></div>
        <h3 style="margin-top:12px">Prioridade sugerida</h3><div><span class="tag azul">${esc(s.prioridade?.valor || "normal")}</span> <span class="peq mut">${esc((s.prioridade?.motivos || []).join("; "))}</span></div>
        ${(s.lacunas || []).length ? `<h3 style="margin-top:12px">Falta perguntar</h3><ul class="lista">${s.lacunas.map(l => `<li>❓ <span>${esc(l.pergunta)}</span></li>`).join("")}</ul>` : ""}`
        : `<div class="mut">Sem sugestão disponível para este chamado.</div>`}
      <div style="margin-top:16px">${pend
        ? `<button class="btn bloco" id="bAceitar">✔ Aceitar sugestão da IA</button><div class="peq mut" style="margin-top:8px">A IA só altera o chamado quando uma pessoa aceita.</div>`
        : `<div class="aviso ok">✅ Triagem confirmada por uma pessoa.</div><button class="btn bloco" id="bDesp" style="margin-top:10px">Ir para o despacho →</button>`}</div></div>
  </div>`;
};
const SJPStatus = s => ({ NOVA: "Nova", ATRIBUIDA: "Atribuída", EM_ANDAMENTO: "Em andamento", BLOQUEADA: "Bloqueada", CONCLUIDA_EXECUTOR: "Aguardando confirmação", RESOLVIDA: "Resolvida", PENDENTE: "Pendente", CANCELADA: "Cancelada" }[s] || s);
VIEWS.triagem_pos = () => {
  if ($("#bIrE")) $("#bIrE").onclick = () => ir("entrada");
  if ($("#bDesp")) $("#bDesp").onclick = () => ir("despacho");
  if ($("#bAceitar")) $("#bAceitar").onclick = async () => {
    $("#bAceitar").disabled = true;
    try { await api("gestor", "POST", `/api/v1/tarefas/${J.os}/ia/decidir`, { aceitar: true }); toast("Triagem confirmada"); rotear(); }
    catch (e) { toast(e.message); $("#bAceitar").disabled = false; }
  };
};

/* ---------------------------------------------------------------- 4. Despacho */
const hav = (a, b) => { const R = 6371, r = x => x * Math.PI / 180, dl = r(b[0] - a[0]), dn = r(b[1] - a[1]);
  const q = Math.sin(dl / 2) ** 2 + Math.cos(r(a[0])) * Math.cos(r(b[0])) * Math.sin(dn / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(q)); };
const CORES = ["#2563eb", "#047857", "#b45309", "#7c3aed", "#be123c", "#0e7490"];
let execs = [];
VIEWS.despacho = async () => {
  await garantirOS();
  const [res, ex] = await Promise.all([api("gestor", "GET", "/api/v1/rota/resumo"), api("gestor", "GET", "/api/v1/cadastros/usuarios?perfil=executor")]);
  execs = ex.filter(e => e.setor_id === 1);
  const t = tarefa, pt = t && t.lat != null ? [t.lat, t.lon] : null;
  const eco = res.economia || {}, paradas = res.rotas.reduce((n, r) => n + r.paradas.length, 0);
  // técnico mais próximo (sugestão)
  let sug = null;
  if (pt) for (const r of res.rotas) for (const p of r.paradas) if (p.lat != null) { const d = hav(pt, [p.lat, p.lon]); if (!sug || d < sug.km) sug = { uid: r.usuario_id, nome: r.tecnico, km: d, parada: p }; }
  const lock = t && t.ia_sugestao?.estado === "pendente";
  const jaAtrib = fase >= 3;
  const escolhido = sug && sug.km <= 8 ? sug.uid : (execs.find(e => e.equipe === (t?.equipe))?.id || execs[0]?.id);
  window._desp = { res, pt, sug };
  return `${cab("Etapa 3 · Chefia", "Despacho inteligente: sem viagem perdida")}
  <div class="grid4">
    ${kpi("Missões abertas no mapa", nf(paradas, 0), "📍", "azul")}
    ${kpi("Km poupados (estimativa)", nf(eco.km_economizados), "🛣️", "verde", "vs. voltar à central a cada OS")}
    ${kpi("Redução de deslocamento (estim.)", nf(eco.percentual) + "%", "📉", "verde")}
    ${kpi("Custo evitado (estimativa)", "R$ " + nf(eco.custo_estimado_economizado, 0), "💰", "ambar", "premissa R$ 1,20/km")}
  </div>
  <div class="duas">
    <div class="card"><div class="eyebrow">Mapa operacional · esquema ilustrativo</div><div id="mapa"></div>
      <div class="legenda"><span><i style="background:#0f1b33"></i>Central</span><span><i style="background:#be123c"></i>Chamado novo</span><span><i style="background:#047857"></i>Missão em aberto</span><span><i style="background:#2563eb"></i>Rota sugerida</span></div>
      <div class="peq mut" style="margin-top:6px">${esc(res.aviso || "")}</div></div>
    <div class="card"><div class="eyebrow">Sugestão do sistema</div>
      ${t ? `<h2 style="margin-top:6px">${sug && sug.km <= 8 ? `${esc(sug.nome)} tem uma missão a ${nf(sug.km)} km deste local` : "Nenhum técnico próximo no momento"}</h2>
        <p class="mut peq">${sug && sug.km <= 8 ? `Encaixar este chamado na mesma saída evita uma viagem de volta à base. (Estimativa com coordenadas aproximadas.)` : "Sugerimos a equipe da categoria."}</p>
        <div style="border-top:1px solid var(--line);margin:12px 0;padding-top:12px"><div class="peq mut">#${t.id} · ${esc(t.tipo || "Sem tipo")} · ${esc(t.prioridade)}</div><h3>${esc(t.titulo)}</h3></div>
        ${jaAtrib ? `<div class="aviso ok">✅ Atribuído a ${esc(t.executor || "técnico")}.</div><button class="btn bloco" id="bTec" style="margin-top:10px">Ver no celular do técnico →</button>`
          : lock ? `<div class="aviso">🔒 <span>Bloqueado até a confirmação da triagem. A chefia não atribui sem uma pessoa conferir a sugestão da IA.</span></div><button class="btn bloco" disabled style="margin-top:10px">Atribuir</button><button class="btn sec bloco" id="bTri" style="margin-top:8px">Abrir triagem</button>`
          : `<label class="c" for="selEx">Técnico</label><select class="in" id="selEx">${execs.map(e => `<option value="${e.id}" ${e.id === escolhido ? "selected" : ""}>${esc(e.avatar)} ${esc(e.nome)} · ${esc(e.equipe || "")}</option>`).join("")}</select>
             <button class="btn bloco" id="bAtrib" style="margin-top:12px">Atribuir ao técnico</button>`}`
        : `<p class="mut">Registre um chamado na aba Entrada para ver a sugestão.</p><button class="btn" id="bIrE">Ir para a Entrada</button>`}
    </div>
  </div>
  <div class="card flat" style="margin-top:14px"><h3>Oportunidades de encaixe</h3>
    <div class="peq mut" style="margin-bottom:8px">Missões de técnicos diferentes a poucos km uma da outra.</div>
    ${res.oportunidades.length ? `<ul class="lista">${res.oportunidades.slice(0, 3).map(o => `<li><span class="n">${nf(o.km)} km</span><span>#${o.a.id} ${esc(o.a.titulo)} ↔ #${o.b.id} ${esc(o.b.titulo)}</span></li>`).join("")}</ul>` : '<div class="mut">Sem oportunidades agora.</div>'}</div>`;
};
VIEWS.despacho_pos = () => {
  desenharMapa();
  if ($("#bIrE")) $("#bIrE").onclick = () => ir("entrada");
  if ($("#bTri")) $("#bTri").onclick = () => ir("triagem");
  if ($("#bTec")) $("#bTec").onclick = () => ir("tecnico");
  if ($("#bAtrib")) $("#bAtrib").onclick = async () => {
    $("#bAtrib").disabled = true;
    try { await api("gestor", "POST", `/api/v1/tarefas/${J.os}/atribuir`, { executor_ids: [+$("#selEx").value] }); toast("Chamado atribuído"); rotear(); }
    catch (e) { toast(e.message); $("#bAtrib").disabled = false; }
  };
};
function desenharMapa() {
  const { res, pt, sug } = window._desp, W = 640, H = 400, P = 36;
  const pts = [[res.central.lat, res.central.lon], ...res.locais.map(l => [l.lat, l.lon])];
  res.rotas.forEach(r => r.paradas.forEach(p => { if (p.lat != null) pts.push([p.lat, p.lon]); })); if (pt) pts.push(pt);
  const la = pts.map(p => p[0]), lo = pts.map(p => p[1]);
  const [a0, a1, o0, o1] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
  const X = lon => P + (lon - o0) / ((o1 - o0) || 1) * (W - 2 * P), Y = lat => H - P - (lat - a0) / ((a1 - a0) || 1) * (H - 2 * P);
  const usados = new Set(); res.rotas.forEach(r => r.paradas.forEach(p => { if (p.lat != null) usados.add(p.lat + "," + p.lon); }));
  let s = `<svg class="mapa" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mapa esquemático com a central, as unidades e as rotas">`;
  for (let i = 1; i < 6; i++) s += `<line x1="${i * W / 6}" y1="0" x2="${i * W / 6}" y2="${H}" stroke="#e8eef8"/>`; for (let i = 1; i < 4; i++) s += `<line x1="0" y1="${i * H / 4}" x2="${W}" y2="${i * H / 4}" stroke="#e8eef8"/>`;
  res.rotas.forEach((r, i) => { const c = CORES[i % CORES.length]; let d = `M${X(res.central.lon)},${Y(res.central.lat)}`; r.paradas.forEach(p => { if (p.lat != null) d += ` L${X(p.lon)},${Y(p.lat)}`; });
    s += `<path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-dasharray="6 5" opacity=".55"/>`; });
  if (pt && sug && sug.km <= 8) s += `<line x1="${X(sug.parada.lon)}" y1="${Y(sug.parada.lat)}" x2="${X(pt[1])}" y2="${Y(pt[0])}" stroke="#2563eb" stroke-width="3" stroke-dasharray="3 5"/>`;
  res.locais.forEach(l => { const on = usados.has(l.lat + "," + l.lon); s += `<circle cx="${X(l.lon)}" cy="${Y(l.lat)}" r="${on ? 7 : 5}" fill="${on ? "#047857" : "#b6c3d8"}"/><text x="${X(l.lon) + 9}" y="${Y(l.lat) + 4}" font-size="11" fill="#5b6b82">${esc(cut(l.nome.replace(/^US |^Escola Municipal /, ""), 22))}</text>`; });
  s += `<circle cx="${X(res.central.lon)}" cy="${Y(res.central.lat)}" r="9" fill="#0f1b33"/><text x="${X(res.central.lon) + 12}" y="${Y(res.central.lat) + 4}" font-size="12" font-weight="700" fill="#0f1b33">Central</text>`;
  if (pt) s += `<circle cx="${X(pt[1])}" cy="${Y(pt[0])}" r="14" fill="#be123c" opacity=".18"/><circle cx="${X(pt[1])}" cy="${Y(pt[0])}" r="8" fill="#be123c"/><text x="${X(pt[1]) + 12}" y="${Y(pt[0]) - 8}" font-size="12" font-weight="700" fill="#be123c">Chamado #${tarefa.id}</text>`;
  $("#mapa").innerHTML = s + "</svg>";
}

/* ---------------------------------------------------------------- 5. Técnico (celular) */
VIEWS.tecnico = async () => {
  await garantirOS();
  const ex = (await api("gestor", "GET", "/api/v1/cadastros/usuarios?perfil=executor")).filter(e => e.setor_id === 1);
  const doChamado = tarefa && tarefa.executor ? ex.find(e => e.nome === tarefa.executor) : null;
  const padrao = (doChamado || ex.find(e => e.login === "exec3") || ex[0]).login;
  window._ex = { ex, padrao };
  return `${cab("Etapa 4 · Em campo", "O técnico, na mão")}
  <div class="duas" style="grid-template-columns:340px 1fr">
    <div><div class="celular"><iframe id="fone" title="App do técnico" src="about:blank"></iframe></div></div>
    <div class="card"><h2>Veja no celular</h2>
      <label class="c" for="selTec">Técnico</label>
      <select class="in" id="selTec">${ex.map(e => `<option value="${e.login}" ${e.login === padrao ? "selected" : ""}>${esc(e.avatar)} ${esc(e.nome)} · ${esc(e.equipe || "")}</option>`).join("")}</select>
      <ul class="lista" style="margin-top:16px">
        <li><span class="n">1</span><span><b>Missões</b><br><span class="peq mut">A fila do técnico, com prioridade e local.</span></span></li>
        <li><span class="n">2</span><span><b>📍 Qual a mais perto de mim?</b><br><span class="peq mut">Ordena pela distância: ir direto à próxima, sem voltar à central.</span></span></li>
        <li><span class="n">3</span><span><b>Iniciar e concluir</b><br><span class="peq mut">Registra o que foi feito e a foto. A OS digital se completa sozinha.</span></span></li>
        <li><span class="n">4</span><span><b>Aba Ajuda</b><br><span class="peq mut">O assistente orienta com base em OS já resolvidas.</span></span></li></ul>
      <div class="linha" style="margin-top:16px"><a class="btn sec" href="/m/" target="_blank" rel="noopener">Abrir em tela cheia ↗</a>${tarefa ? `<a class="btn sec" href="/os/${tarefa.id}" target="_blank" rel="noopener">📄 OS digital #${tarefa.id} ↗</a>` : ""}</div>
      <p class="peq mut" style="margin-top:12px">Dica: ao abrir pelo link público (HTTPS) o celular real também libera GPS e câmera.</p></div>
  </div>`;
};
VIEWS.tecnico_pos = () => {
  async function carregar(login) {
    try { await fazerLogin(login); localStorage.setItem("tk", tokens[login]); localStorage.setItem("us", JSON.stringify(users[login])); $("#fone").src = "/m/?t=" + Date.now(); }
    catch (e) { toast(e.message); }
  }
  $("#selTec").onchange = e => carregar(e.target.value);
  carregar(window._ex.padrao);
};

/* ---------------------------------------------------------------- 6. Resultado */
VIEWS.resultado = async () => {
  const [c, rk, b] = await Promise.all([api("gestor", "GET", "/api/v1/indicadores/confiabilidade"), api("gestor", "GET", "/api/v1/gamificacao/ranking"), api("gestor", "GET", "/api/v1/indicadores/baseline")]);
  const dias = c.os_abertas.por_dia_30d || [], max = Math.max(1, ...dias.map(d => d.n));
  const v = c.os_abertas.variacao_percentual;
  const h = b.horas_ate_conclusao || {};
  return `${cab("Etapa 5 · Gestão", "O que o gestor passa a enxergar")}
  <div class="grid4">
    ${kpi("OS abertas · 30 dias", nf(c.os_abertas.ultimos_30_dias, 0), "📥", "azul", "dados fictícios de demonstração")}
    ${kpi("MTTR · tempo até restabelecer", nf(c.mttr.horas_media) + " h", "🛠️", "verde", `mediana ${nf(c.mttr.horas_mediana)} h · ${c.mttr.amostra} OS`)}
    ${kpi("MTBF · tempo entre falhas", c.mtbf.dias_media == null ? "—" : nf(c.mtbf.dias_media) + " d", "⏳", "", `${c.mtbf.ativos_com_reincidencia} ativos com reincidência`)}
    ${kpi("Recorrência de OS", nf(c.recorrencia.taxa_percentual) + "%", "🔁", "ambar", `${c.recorrencia.os_recorrentes} repetidas · ${c.recorrencia.os_reabertas} reabertas`)}
  </div>
  <div class="duas">
    <div class="card"><h2>OS abertas por dia (30 dias)</h2><div class="barras" role="img" aria-label="Barras com a quantidade de OS abertas por dia">${dias.map(d => `<div style="height:${Math.round(d.n / max * 100)}%" title="${d.dia}: ${d.n}"></div>`).join("") || '<span class="mut">Sem dados.</span>'}</div>
      <div class="peq mut" style="margin-top:8px">Passe o mouse nas barras para ver o dia.</div>
      <h3 style="margin-top:18px">Onde o problema se repete</h3>
      ${c.recorrencia.ranking.length ? `<ul class="lista">${c.recorrencia.ranking.slice(0, 3).map(r => `<li><span class="n">${r.repeticoes}×</span><span><b>${esc(r.onde)}</b> · ${esc(r.tipo)}<br><span class="peq mut">${esc(r.acao)}</span></span></li>`).join("")}</ul>` : '<div class="mut">Sem repetições.</div>'}</div>
    <div class="card"><h2>Ranking do período</h2><div class="peq mut" style="margin-bottom:10px">Pontos por qualidade, prazo e avaliação de quem pediu. ${esc(rk.periodo?.nome || "")}</div>
      <ol class="rank" style="padding:0;margin:0">${(rk.itens || []).slice(0, 5).map(i => `<li><span class="pos">${i.posicao}º</span><span class="av" aria-hidden="true">${esc(i.avatar)}</span><span><b>${esc(i.nome)}</b><br><span class="peq mut">${esc(i.equipe || "")}</span></span><b>${nf(i.pontos, 0)} pts</b></li>`).join("")}</ol>
      <div class="aviso info" style="margin-top:12px">⭐ Avaliação média de quem pediu: <b>${nf(c.avaliacoes.media, 1)}</b> (${c.avaliacoes.amostra} avaliações)</div></div>
  </div>
  <div class="card flat" style="margin-top:14px"><h3>Antes da plataforma · Help Desk de TI (dados reais, ${esc(b.periodo)})</h3>
    <div class="peq mut">${nf(b.chamados, 0)} chamados · mediana ${nf(h.mediana)} h · média ${nf(h.media)} h · 90% concluídos em até ${nf(h.p90, 0)} h · ${nf(b.percentual_conclusao_acima_de_72h)}% acima de 72 h. Os números acima são da demonstração (fictícios).</div></div>`;
};

/* ---------------------------------------------------------------- 7. Assistente */
const Q1 = "O leitor de código de barras do almoxarifado não lê as etiquetas";
const Q2 = "O leitor de código de barras não está lendo as etiquetas dos bens";
const SOLUCAO = "Leitor estava configurado para o padrão de código errado. Reconfigurei para Code 128 lendo o código de configuração do manual, limpei a janela de leitura e atualizei o driver. Testei com 10 etiquetas, todas lidas.";
let passoIA = J.passoIA || 0;
VIEWS.assistente = async () => `
  ${cab("Pilar 1 · IA que se alimenta", "A IA aprende com cada OS concluída")}
  <div class="duas">
    <div class="card"><h2>Assistente do técnico</h2>
      <div class="chat" id="chat" aria-live="polite"></div>
      <form id="fq" class="linha" style="margin-top:12px;flex-wrap:nowrap"><input class="in" id="qIn" placeholder="Pergunte algo, como um técnico faria…" aria-label="Pergunta ao assistente"><button class="btn" type="submit">Enviar</button></form></div>
    <div class="card"><h2>Mostre o ciclo em 3 passos</h2><div class="mut peq" style="margin-bottom:12px">Nada aqui é de mentira: o passo 2 cria, atribui e conclui uma OS pelo sistema.</div>
      <div class="linha" style="flex-direction:column;align-items:stretch;gap:10px">
        <button class="btn" id="p1">① Perguntar algo que a IA não conhece</button>
        <button class="btn" id="p2">② Um técnico resolve a OS</button>
        <button class="btn" id="p3">③ Perguntar de novo, no mesmo chat</button>
        <div class="peq mut">Para repetir a demonstração, clique em <b>Reiniciar</b>.</div></div>
      <div class="log" id="log" style="margin-top:14px" aria-live="polite">Aguardando…</div></div>
  </div>`;
VIEWS.assistente_pos = () => {
  const chat = $("#chat"), log = $("#log");
  const pintar = () => { chat.innerHTML = msgs.map(m => m.u ? `<div class="msg u">${esc(m.u)}</div>` :
    `<div class="msg b ${m.sabe ? "sabe" : "nao"}">${md(m.t)}${m.fontes?.length ? `<div class="fontes">${m.fontes.map(f => `<span class="tag ${f.tipo === "os" ? "azul" : ""}">${f.tipo === "os" ? "OS #" + f.id : "Procedimento"} · ${cut(f.titulo, 28)} · ${Math.round(f.score * 100)}%</span>`).join("")}</div>` : ""}
      ${m.id ? `<div class="linha" style="margin-top:8px"><button class="chip-b" data-fb="1" data-id="${m.id}">👍 Ajudou</button><button class="chip-b" data-fb="0" data-id="${m.id}">👎 Não ajudou</button></div>` : ""}</div>`).join("") || '<div class="mut">Faça uma pergunta ou use os 3 passos ao lado.</div>';
    chat.scrollTop = chat.scrollHeight;
    chat.querySelectorAll("[data-fb]").forEach(b => b.onclick = async () => { try { await api("gestor", "POST", `/api/v1/chat/${b.dataset.id}/feedback`, { resolveu: b.dataset.fb === "1" }); toast("Obrigado pelo retorno"); b.parentElement.remove(); } catch (e) { toast(e.message); } }); };
  async function perguntar(q) {
    msgs.push({ u: q }); pintar();
    const r = await api("gestor", "POST", "/api/v1/chat", { mensagem: q });
    const sabe = r.modo !== "sem caso parecido";
    msgs.push({ t: r.resposta, sabe, fontes: sabe ? (r.fontes || []).slice(0, 3) : [], id: r.conversa_id }); pintar();
    return sabe;
  }
  const L = (t, ok) => { log.innerHTML += `<div>${ok ? '<span class="ok">✔</span> ' : "› "}${esc(t)}</div>`; };
  $("#fq").onsubmit = async e => { e.preventDefault(); const v = $("#qIn").value.trim(); if (v.length < 3) return; $("#qIn").value = ""; try { await perguntar(v); } catch (er) { toast(er.message); } };
  $("#p1").onclick = async () => { try { const s = await perguntar(Q1); log.innerHTML = ""; L(s ? "A IA já conhecia este caso (use Reiniciar para ver o ciclo do zero)." : "A IA admitiu que ainda não tem um caso parecido.", true); } catch (e) { toast(e.message); } };
  $("#p3").onclick = async () => { try { const s = await perguntar(Q2); L(s ? "Agora a IA responde, citando a OS que acabou de ser resolvida." : "A IA ainda não encontrou o caso: confira se o passo 2 foi executado.", s); } catch (e) { toast(e.message); } };
  $("#p2").onclick = async () => {
    const b = $("#p2"); b.disabled = true; log.innerHTML = "";
    try {
      L("Atendente registra o chamado…");
      const t = await api("atendente1", "POST", "/api/v1/tarefas", { titulo: "Leitor de código de barras não lê as etiquetas", descricao: "O leitor do almoxarifado não reconhece as etiquetas dos bens patrimoniais; nenhuma leitura é concluída.", setor_id: 1,
        local: "Almoxarifado", unidade_demandante: "Almoxarifado Central (fictício)", solicitante_nome: "Servidor do almoxarifado (fictício)", solicitante_contato: "ramal 2100" });
      L(`OS #${t.id} criada`, true);
      try { await api("gestor", "POST", `/api/v1/tarefas/${t.id}/ia/decidir`, { aceitar: true }); L("Gestor confirmou a triagem da IA", true); } catch (e) {}
      const ex = await api("gestor", "GET", "/api/v1/cadastros/usuarios?perfil=executor"); const tec = ex.find(x => x.login === "exec1") || ex[0];
      await api("gestor", "POST", `/api/v1/tarefas/${t.id}/atribuir`, { executor_ids: [tec.id] }); L(`Atribuída a ${tec.nome}`, true);
      await api("exec1", "POST", `/api/v1/tarefas/${t.id}/iniciar`, {}); L("Técnico iniciou o atendimento", true);
      const fd = new FormData(); fd.append("descricao", SOLUCAO); fd.append("arquivos", await fotoDemo(), "evidencia.png");
      await api("exec1", "POST", `/api/v1/tarefas/${t.id}/concluir`, fd); L("Técnico concluiu e registrou a solução + foto", true);
      L("Pronto: a solução já está na base do assistente. Faça o passo ③.", true);
    } catch (e) { L("Erro: " + e.message); } finally { b.disabled = false; }
  };
  pintar();
};
function fotoDemo() {
  return new Promise(res => { const c = document.createElement("canvas"); c.width = 480; c.height = 300; const g = c.getContext("2d");
    g.fillStyle = "#e0eaff"; g.fillRect(0, 0, 480, 300); g.fillStyle = "#2563eb"; g.fillRect(40, 90, 400, 120); g.fillStyle = "#fff"; g.font = "bold 26px Arial"; g.textAlign = "center";
    g.fillText("Foto de demonstração", 240, 140); g.font = "18px Arial"; g.fillText("leitor testado: 10 de 10 etiquetas", 240, 180); c.toBlob(b => res(b), "image/png"); });
}

/* ---------------------------------------------------------------- roteiro e reinício */
const ROTEIRO = [["0:00", "Por quê", "Abra com o técnico que resolve o mesmo problema várias vezes enquanto o conhecimento fica preso no papel e na cabeça de cada um. Mostre a Visão geral: 22,9% dos chamados passam de 72 h."],
  ["0:35", "Como", "Os quatro pilares em ciclo: quem registra mais e melhor deixa a OS completa; a OS completa alimenta a IA; a IA reduz repetição; o resultado vira algo que o secretário mostra."],
  ["1:10", "O quê", "Aba Assistente: ① perguntar algo que a IA não conhece, ② um técnico resolve a OS, ③ perguntar de novo e ver a resposta citar a OS."],
  ["2:10", "Resultado", "Aba Resultado: OS abertas, MTTR, MTBF, recorrência e ranking. Diga que os números da tela são fictícios e que o diagnóstico é real."],
  ["2:40", "Pedido", "Piloto de 30 dias com uma equipe, medindo OS abertas, recorrência, MTTR/MTBF e avaliação."]];
$("#bRoteiro").onclick = () => { $("#dlgConteudo").innerHTML = `<h2>Roteiro de 3 minutos</h2><div class="rot-t">${ROTEIRO.map(r => `<b>${r[0]}</b><span><b style="color:inherit">${r[1]}.</b> ${esc(r[2])}</span>`).join("")}</div>
  <div class="aviso info">Se algo falhar ao vivo: clique em Reiniciar e comece de novo, ou use o vídeo de reserva.</div><div class="linha" style="margin-top:14px"><button class="btn" id="fecha">Fechar</button></div>`;
  $("#dlg").showModal(); $("#fecha").onclick = () => $("#dlg").close(); };
$("#bReiniciar").onclick = async () => {
  const b = $("#bReiniciar"); b.disabled = true;
  try { await fetch("/api/v1/demo/reiniciar", { method: "POST" }).then(r => { if (!r.ok) throw new Error("Reinício desativado neste ambiente."); });
    Object.keys(tokens).forEach(k => delete tokens[k]); J = {}; salvarJ(); msgs = []; try { localStorage.removeItem("tk"); localStorage.removeItem("us"); localStorage.removeItem("fila"); localStorage.removeItem("cacheM"); } catch (e) {}
    toast("Demonstração reiniciada"); if (location.hash === "#/geral" || !location.hash) rotear(); else ir("geral"); }
  catch (e) { toast(e.message); } finally { b.disabled = false; }
};
rotear();
