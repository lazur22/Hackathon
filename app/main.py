"""Missão SJP — plataforma genérica de missões, acompanhamento de tarefas e valorização das equipes municipais."""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, OUTBOX_INTERVALO_S, SEED_ON_START, UPLOAD_DIR
from .db import Base, SessionLocal, engine
from .routers import auth, cadastros, gamificacao, indicadores, integracao, notificacoes, tarefas, validar
from .seed import semear
from .services import outbox
from .services.erros import ErroNegocio

log = logging.getLogger("missao")


async def _worker_outbox():
    """Entrega periódica das atualizações ao sistema de origem (retry com backoff)."""
    while True:
        try:
            await asyncio.to_thread(_rodada)
        except Exception as e:  # nunca derruba o worker
            log.warning("worker outbox: %s", e)
        await asyncio.sleep(OUTBOX_INTERVALO_S)


def _rodada():
    with SessionLocal() as db:
        outbox.processar(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    (BASE_DIR / "data").mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    if SEED_ON_START:
        with SessionLocal() as db:
            semear(db)
    tarefa = asyncio.create_task(_worker_outbox())
    yield
    tarefa.cancel()


app = FastAPI(title="Missão SJP", version="1.0.0", lifespan=lifespan,
              description="Plataforma genérica de missões para a Prefeitura de São José dos Pinhais (protótipo do Hackathon SJP).")


@app.exception_handler(ErroNegocio)
async def _erro_negocio(_: Request, e: ErroNegocio):
    return JSONResponse({"detail": e.mensagem}, status_code=e.status)


for r in (auth, cadastros, tarefas, validar, integracao, gamificacao, indicadores, notificacoes):
    app.include_router(r.router)


@app.get("/saude", tags=["Infra"])
def saude():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(BASE_DIR / "web" / "launcher.html")


@app.get("/validar/{token}", include_in_schema=False)
def pagina_validar(token: str):
    return FileResponse(BASE_DIR / "validar" / "index.html")


@app.get("/m/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(BASE_DIR / "mobile" / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/m/"})


app.mount("/web", StaticFiles(directory=BASE_DIR / "web", html=True), name="web")
app.mount("/m", StaticFiles(directory=BASE_DIR / "mobile", html=True), name="mobile")
app.mount("/static", StaticFiles(directory=BASE_DIR / "validar"), name="static_validar")
