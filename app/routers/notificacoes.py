"""Notificações: caixa de entrada, stream em tempo real (SSE) e assinatura Web Push."""
from __future__ import annotations
import asyncio
import json
import queue

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notificacao, PushSub, Usuario
from ..security import usuario_atual
from ..services import notify

router = APIRouter(prefix="/api/v1", tags=["Notificações"])


@router.get("/notificacoes")
def listar(somente_nao_lidas: bool = False, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = select(Notificacao).where(Notificacao.usuario_id == u.id).order_by(Notificacao.id.desc()).limit(50)
    if somente_nao_lidas:
        q = q.where(Notificacao.lida.is_(False))
    itens = db.scalars(q).all()
    return {"nao_lidas": sum(1 for n in itens if not n.lida),
            "itens": [{"id": n.id, "titulo": n.titulo, "corpo": n.corpo, "tarefa_id": n.tarefa_id, "lida": n.lida,
                       "em": n.criada_em.isoformat() + "Z"} for n in itens]}


@router.post("/notificacoes/lidas")
def marcar_lidas(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    db.execute(update(Notificacao).where(Notificacao.usuario_id == u.id).values(lida=True))
    db.commit()
    return {"ok": True}


@router.get("/stream")
async def stream(request: Request, u: Usuario = Depends(usuario_atual)):
    """SSE: o app mobile abre este canal e recebe a missão em tempo real (autenticação via ?t=)."""
    q = notify.assinar(u.id)
    loop = asyncio.get_running_loop()

    async def gerador():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await loop.run_in_executor(None, lambda: q.get(True, 15))
                    yield f"event: notificacao\ndata: {json.dumps(item)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            notify.desassinar(u.id, q)

    return StreamingResponse(gerador(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ Web Push
@router.get("/push/chave")
def chave_publica(u: Usuario = Depends(usuario_atual)):
    c = notify.chaves_vapid()
    return {"disponivel": bool(c), "chave_publica": c["public"] if c else None}


class Assinatura(BaseModel):
    endpoint: str
    keys: dict


@router.post("/push/assinar")
def assinar(d: Assinatura, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    sub = db.scalar(select(PushSub).where(PushSub.endpoint == d.endpoint))
    if sub:
        sub.usuario_id, sub.p256dh, sub.auth = u.id, d.keys.get("p256dh", ""), d.keys.get("auth", "")
    else:
        db.add(PushSub(usuario_id=u.id, endpoint=d.endpoint, p256dh=d.keys.get("p256dh", ""), auth=d.keys.get("auth", "")))
    db.commit()
    return {"ok": True}
