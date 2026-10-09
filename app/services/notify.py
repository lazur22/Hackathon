"""Notificações: caixa de entrada + tempo real (SSE) + Web Push opcional.

* Push que avisa o EXECUTOR (este módulo) é diferente da integração que sincroniza o LEGADO (outbox.py).
* SSE funciona em qualquer rede interna, sem passar por serviço de terceiros.
* Web Push padrão (VAPID) funciona com o app fechado, mas o aviso trafega pelo serviço de push do navegador
  (Google/Mozilla/Apple). Para soberania total no datacenter, ver docs/ARQUITETURA.md (ntfy/UnifiedPush).
"""
from __future__ import annotations
import base64
import json
import logging
import queue
import threading
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..config import VAPID_CONTATO, VAPID_FILE
from ..models import Notificacao, PushSub

log = logging.getLogger("missao.notify")

_subs: dict[int, list[queue.SimpleQueue]] = {}
_lock = threading.Lock()


def assinar(usuario_id: int) -> queue.SimpleQueue:
    q: queue.SimpleQueue = queue.SimpleQueue()
    with _lock:
        _subs.setdefault(usuario_id, []).append(q)
    return q


def desassinar(usuario_id: int, q: queue.SimpleQueue) -> None:
    with _lock:
        if q in _subs.get(usuario_id, []):
            _subs[usuario_id].remove(q)


def _publicar(usuario_id: int, dados: dict) -> None:
    with _lock:
        for q in list(_subs.get(usuario_id, [])):
            q.put(dados)


def notificar(db: Session, usuario_id: Optional[int], titulo: str, corpo: str = "", tarefa_id: Optional[int] = None) -> None:
    """Grava na caixa de entrada e agenda a entrega em tempo real para DEPOIS do commit."""
    if not usuario_id:
        return
    n = Notificacao(usuario_id=usuario_id, titulo=titulo[:160], corpo=corpo[:400], tarefa_id=tarefa_id)
    db.add(n)
    db.info.setdefault("fila_notif", []).append((usuario_id, titulo, corpo, tarefa_id, n))


@event.listens_for(Session, "after_commit")
def _depois_do_commit(session: Session) -> None:
    fila = session.info.pop("fila_notif", [])
    for usuario_id, titulo, corpo, tarefa_id, n in fila:
        dados = {"id": n.id, "titulo": titulo, "corpo": corpo, "tarefa_id": tarefa_id}
        _publicar(usuario_id, dados)
        threading.Thread(target=_web_push, args=(usuario_id, dados), daemon=True).start()


@event.listens_for(Session, "after_rollback")
def _rollback(session: Session) -> None:
    session.info.pop("fila_notif", None)


# ------------------------------------------------------------------ Web Push (opcional)
_vapid_cache: Optional[dict] = None
_vapid_lock = threading.Lock()


def chaves_vapid() -> Optional[dict]:
    """Gera (uma única vez, com trava) o par de chaves VAPID; persiste em data/vapid.json."""
    global _vapid_cache
    with _vapid_lock:
        if _vapid_cache:
            return _vapid_cache
        try:
            from py_vapid import Vapid
            from cryptography.hazmat.primitives import serialization
        except Exception:
            return None
        try:
            if VAPID_FILE.exists() and VAPID_FILE.stat().st_size > 0:
                _vapid_cache = json.loads(VAPID_FILE.read_text())
                return _vapid_cache
            v = Vapid()
            v.generate_keys()
            priv_pem = v.private_pem().decode()
            pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            dados = {"public": base64.urlsafe_b64encode(pub).rstrip(b"=").decode(), "private_pem": priv_pem}
            VAPID_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = VAPID_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(dados))
            tmp.replace(VAPID_FILE)          # escrita atômica
            _vapid_cache = dados
            return dados
        except Exception as e:  # pragma: no cover
            log.warning("VAPID indisponível: %s", e)
            return None


def _web_push(usuario_id: int, dados: dict) -> None:
    from ..db import SessionLocal
    chaves = chaves_vapid()
    if not chaves:
        return
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        return
    with SessionLocal() as db:
        subs = db.query(PushSub).filter(PushSub.usuario_id == usuario_id).all()
        for s in subs:
            try:
                webpush(
                    subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                    data=json.dumps(dados),
                    vapid_private_key=chaves["private_pem"],
                    vapid_claims={"sub": VAPID_CONTATO},
                    timeout=5,
                )
            except WebPushException as e:  # assinatura expirada -> remove
                if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
                    db.delete(s)
                    db.commit()
            except Exception as e:  # rede interna sem acesso ao serviço de push: tolerado
                log.info("Web Push não entregue (%s); SSE continua ativo", e)
