"""HELP DESK MUNICIPAL — LEGADO SIMULADO.

Representa o sistema que a Prefeitura já usa: o ATENDENTE recebe a ligação e cadastra o chamado aqui.
Ao salvar, o legado chama a API da plataforma (entrada). A plataforma devolve andamento, impedimentos,
conclusão e validação pelo webhook /webhook/plataforma (saída).

Botão "Simular queda do legado": o webhook passa a responder 503 — a plataforma mantém as atualizações na
fila e reenvia depois, sem perder nem duplicar (idempotência pela `chave_idempotencia`).
Os status usam o vocabulário do legado real (ABERTO, ENCAMINHAR, EM EXECUCAO, EXECUTADO, CONCLUIDO, REABERTO, CANCELADO).
"""
from __future__ import annotations
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
DB = os.getenv("LEGADO_DB", str(BASE / "legado.db"))
PLATAFORMA = os.getenv("PLATAFORMA_URL", "http://localhost:8000")
API_KEY = os.getenv("LEGADO_API_KEY", "demo-legado-key")
WEBHOOK_KEY = os.getenv("LEGADO_WEBHOOK_KEY", "demo-webhook-key")

_lock = threading.Lock()
_estado = {"fora_do_ar": False}

app = FastAPI(title="Help Desk Municipal — legado simulado")


def conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS chamados(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ano INTEGER, solicitante TEXT, depto TEXT, ramal TEXT, local TEXT,
          problema TEXT, descricao TEXT, status TEXT DEFAULT 'ABERTO', atendente TEXT,
          aberto_em TEXT, atualizado_em TEXT, plataforma_id INTEGER, envio TEXT DEFAULT 'pendente', envio_msg TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS atualizacoes(
          id INTEGER PRIMARY KEY AUTOINCREMENT, chamado_id INTEGER, chave TEXT UNIQUE, evento TEXT, status TEXT,
          texto TEXT, ator TEXT, em TEXT, recebido_em TEXT, extra TEXT);
        """)


init()


def agora():
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")


class Novo(BaseModel):
    solicitante: str
    depto: str = ""
    ramal: str = ""
    local: str = ""
    problema: str
    descricao: str = ""
    atendente: str = "Atendente Help Desk"
    login_solicitante: str | None = None


def enviar_para_plataforma(chamado_id: int) -> dict:
    """Job de integração do legado: envia o chamado recém-cadastrado à plataforma (idempotente por id_origem)."""
    with _lock, conn() as c:
        ch = c.execute("SELECT * FROM chamados WHERE id=?", (chamado_id,)).fetchone()
    corpo = {"id_origem": str(ch["id"]), "titulo": ch["problema"], "descricao": ch["descricao"], "unidade": ch["depto"],
             "local": ch["local"], "atendente": ch["atendente"],
             "solicitante": {"nome": ch["solicitante"], "contato": ch["ramal"],
                             **({"login": os.getenv("DEMO_LOGIN")} if os.getenv("DEMO_LOGIN") else {})}}
    try:
        r = httpx.post(f"{PLATAFORMA}/api/v1/integracao/tarefas", json=corpo, headers={"X-API-Key": API_KEY}, timeout=8)
        if r.status_code >= 300:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
        j = r.json()
        with _lock, conn() as c:
            c.execute("UPDATE chamados SET plataforma_id=?, envio='enviado', envio_msg=? WHERE id=?",
                      (j["id_plataforma"], "duplicada (ignorada)" if j.get("duplicada") else "ok", chamado_id))
        return {"ok": True, **j}
    except Exception as e:
        with _lock, conn() as c:
            c.execute("UPDATE chamados SET envio='erro', envio_msg=? WHERE id=?", (str(e)[:200], chamado_id))
        return {"ok": False, "erro": str(e)}


@app.post("/api/chamados", status_code=201)
def abrir(d: Novo):
    with _lock, conn() as c:
        cur = c.execute(
            "INSERT INTO chamados(ano,solicitante,depto,ramal,local,problema,descricao,atendente,aberto_em,atualizado_em)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().year, d.solicitante, d.depto, d.ramal, d.local, d.problema, d.descricao, d.atendente, agora(), agora()))
        cid = cur.lastrowid
    return {"id": cid, "integracao": enviar_para_plataforma(cid)}


@app.post("/api/chamados/{cid}/reenviar")
def reenviar(cid: int):
    return enviar_para_plataforma(cid)


@app.get("/api/chamados")
def listar():
    with _lock, conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM chamados ORDER BY id DESC LIMIT 100")]
        for r in rows:
            r["atualizacoes"] = [dict(a) for a in c.execute(
                "SELECT * FROM atualizacoes WHERE chamado_id=? ORDER BY id", (r["id"],))]
    return {"fora_do_ar": _estado["fora_do_ar"], "chamados": rows}


class Queda(BaseModel):
    fora_do_ar: bool


@app.post("/api/simular-queda")
def queda(d: Queda):
    _estado["fora_do_ar"] = d.fora_do_ar
    return _estado


@app.post("/webhook/plataforma")
def webhook(p: dict, x_api_key: str | None = Header(default=None)):
    """Saída da plataforma → legado. Idempotente: a mesma chave repetida é aceita e ignorada."""
    if x_api_key != WEBHOOK_KEY:
        raise HTTPException(401, "chave inválida")
    if _estado["fora_do_ar"]:
        return JSONResponse({"detail": "Legado indisponível (simulado)"}, status_code=503)
    with _lock, conn() as c:
        ja = c.execute("SELECT 1 FROM atualizacoes WHERE chave=?", (p["chave_idempotencia"],)).fetchone()
        if ja:
            return {"ok": True, "duplicada": True}
        ch = c.execute("SELECT id FROM chamados WHERE id=?", (int(p["id_origem"]),)).fetchone()
        if not ch:
            raise HTTPException(404, "chamado de origem inexistente")
        extra = ""
        if p.get("impedimento"):
            extra = f"IMPEDIMENTO[{p['impedimento']['tipo']}]"
        if p.get("validacao") and p["validacao"].get("nota"):
            extra = f"nota {p['validacao']['nota']}/5"
        c.execute("INSERT INTO atualizacoes(chamado_id,chave,evento,status,texto,ator,em,recebido_em,extra) VALUES(?,?,?,?,?,?,?,?,?)",
                  (ch["id"], p["chave_idempotencia"], p["evento"], p["status_legado"], p["texto"], p["ator"],
                   p["ocorrido_em"], agora(), extra))
        c.execute("UPDATE chamados SET status=?, atualizado_em=? WHERE id=?", (p["status_legado"], agora(), ch["id"]))
    return {"ok": True, "duplicada": False}


@app.get("/saude")
def saude():
    return {"status": "ok", "fora_do_ar": _estado["fora_do_ar"]}


@app.get("/")
def pagina():
    return FileResponse(BASE / "index.html")
