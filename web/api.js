/* Cliente de API + utilidades compartilhadas (web e mobile). Sem dependências. */
const SJP = (() => {
  const st = { token: null, user: null };
  try { st.token = localStorage.getItem("tk"); st.user = JSON.parse(localStorage.getItem("us") || "null"); } catch (e) {}

  const STATUS = {
    NOVA: ["🆕", "Nova"], ATRIBUIDA: ["🎯", "Atribuída"], EM_ANDAMENTO: ["▶️", "Em andamento"], BLOQUEADA: ["⛔", "Bloqueada"],
    CONCLUIDA_EXECUTOR: ["⏳", "Aguardando confirmação"], RESOLVIDA: ["🏆", "Resolvida"], PENDENTE: ["↩️", "Pendente"], CANCELADA: ["✖️", "Cancelada"]
  };
  const PRIO = { urgente: "🔴 Urgente", alta: "🟠 Alta", normal: "⚪ Normal", baixa: "🟢 Baixa" };
  const IMP = { material: "Falta de material/equipamento", terceiro: "Dependência de terceiro", acesso: "Sem acesso ao local/sistema",
                apoio: "Preciso de apoio de outra equipe", divergencia: "Problema diferente do informado", outro: "Outro" };

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = s => { const [i, t] = STATUS[s] || ["", s]; return `<span class="chip s-${s}">${i} ${t}</span>`; };
  const fdt = iso => iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  const dur = min => min == null ? "—" : min < 90 ? `${Math.round(min)} min` : min < 2880 ? `${(min / 60).toFixed(1)} h` : `${(min / 1440).toFixed(1)} d`;

  async function req(method, path, body, opts = {}) {
    const h = {};
    if (st.token) h.Authorization = "Bearer " + st.token;
    let b;
    if (body instanceof FormData) b = body;
    else if (body !== undefined) { h["Content-Type"] = "application/json"; b = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, { method, headers: h, body: b }); }
    catch (e) { const err = new Error("Sem conexão com o servidor."); err.rede = true; throw err; }
    if (r.status === 401 && !opts.semLogout) { sair(false); location.reload(); throw new Error("Sessão expirada."); }
    let j = null; try { j = await r.json(); } catch (e) {}
    if (!r.ok) { const err = new Error(typeof j?.detail === "string" ? j.detail : (j?.detail?.[0]?.msg || "Erro " + r.status)); err.status = r.status; throw err; }
    return j;
  }
  const get = p => req("GET", p), post = (p, b) => req("POST", p, b === undefined ? {} : b), put = (p, b) => req("PUT", p, b), patch = (p, b) => req("PATCH", p, b);

  async function login(l, s) {
    const j = await req("POST", "/api/v1/auth/login", { login: l, senha: s }, { semLogout: true });
    st.token = j.token; st.user = j.usuario;
    localStorage.setItem("tk", j.token); localStorage.setItem("us", JSON.stringify(j.usuario));
    return j.usuario;
  }
  function sair(chamar = true) {
    if (chamar && st.token) fetch("/api/v1/auth/sair", { method: "POST", headers: { Authorization: "Bearer " + st.token } }).catch(() => {});
    st.token = null; st.user = null; localStorage.removeItem("tk"); localStorage.removeItem("us");
  }
  const tem = (...ps) => !!st.user && (st.user.perfis.includes("admin") || ps.some(p => st.user.perfis.includes(p)));

  function toast(msg, ms = 3200) {
    document.querySelectorAll(".toast").forEach(t => t.remove());
    const t = document.createElement("div"); t.className = "toast pop"; t.setAttribute("role", "status"); t.textContent = msg;
    document.body.appendChild(t); setTimeout(() => t.remove(), ms);
  }
  function stream(onMsg) {                    // SSE: notificações em tempo real (auth via ?t=)
    if (!st.token || !window.EventSource) return null;
    const es = new EventSource("/api/v1/stream?t=" + encodeURIComponent(st.token));
    es.addEventListener("notificacao", e => { try { onMsg(JSON.parse(e.data)); } catch (x) {} });
    return es;
  }
  function fonte() {                          // acessibilidade: aumentar fonte
    const g = document.body.classList.toggle("grande"); try { localStorage.setItem("fonte", g ? "1" : "0"); } catch (e) {}
  }
  try { if (localStorage.getItem("fonte") === "1") document.addEventListener("DOMContentLoaded", () => document.body.classList.add("grande")); } catch (e) {}
  return { st, req, get, post, put, patch, login, sair, tem, esc, chip, fdt, dur, toast, stream, fonte, STATUS, PRIO, IMP };
})();
