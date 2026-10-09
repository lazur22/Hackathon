"""Integração de saída (plataforma -> sistema de origem).

Garantias:
* Persistência: cada atualização vira uma linha na tabela `outbox` na MESMA transação do evento (nada se perde).
* Falha temporária: se o legado estiver fora, a mensagem fica `pendente` com backoff exponencial e é reenviada.
* Ordem: mensagens da mesma tarefa são entregues em sequência (uma pendente bloqueia as seguintes).
* Sem duplicidade: cada mensagem tem `chave` única; o destino a usa para ignorar reenvios (idempotência).
"""
from __future__ import annotations
import logging
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Outbox, SistemaOrigem, Tarefa, agora

log = logging.getLogger("missao.outbox")

LEGADO = {  # estados da plataforma -> vocabulário do Help Desk legado (observado nos arquivos de chamados/OS)
    "NOVA": "ABERTO",
    "ATRIBUIDA": "ENCAMINHAR",
    "EM_ANDAMENTO": "EM EXECUCAO",
    "BLOQUEADA": "EM EXECUCAO",
    "CONCLUIDA_EXECUTOR": "EXECUTADO",
    "RESOLVIDA": "CONCLUIDO",
    "PENDENTE": "REABERTO",
    "CANCELADA": "CANCELADO",
}


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


def enfileirar(db: Session, tarefa: Tarefa, evento: str, texto: str, ator: str, extra: dict | None = None) -> None:
    if not tarefa.origem_sistema_id:
        return
    sistema = tarefa.origem_sistema or db.get(SistemaOrigem, tarefa.origem_sistema_id)
    if not sistema or not sistema.ativo or not sistema.webhook_url:
        return
    seq = db.scalar(select(func.count()).select_from(Outbox).where(Outbox.tarefa_id == tarefa.id)) or 0
    seq += 1
    chave = f"{sistema.codigo}:{tarefa.origem_id}:{seq}"
    exec_nomes = [p.usuario.nome for p in tarefa.participantes if p.ativo]
    payload = {
        "chave_idempotencia": chave,
        "sequencia": seq,
        "sistema_origem": sistema.codigo,
        "id_origem": tarefa.origem_id,          # vínculo com o registro de origem
        "id_plataforma": tarefa.id,
        "evento": evento,
        "status_plataforma": tarefa.status,
        "status_legado": LEGADO.get(tarefa.status, tarefa.status),
        "texto": texto,
        "ator": ator,
        "ocorrido_em": iso(agora()),
        "executores": exec_nomes,
        "validacao": {"resolvido": tarefa.status == "RESOLVIDA", "nota": tarefa.avaliacao,
                      "comentario": tarefa.comentario_avaliacao} if tarefa.avaliacao or evento in ("resolvida", "pendencia") else None,
    }
    if extra:
        payload.update(extra)
    db.add(Outbox(sistema_id=sistema.id, tarefa_id=tarefa.id, chave=chave, payload=payload))


def processar(db: Session, cliente: httpx.Client | None = None) -> dict:
    """Uma rodada de entrega. Chamada pelo worker periódico e pelo botão 'sincronizar agora'."""
    cliente = cliente or httpx.Client(timeout=5)
    enviados = falhas = 0
    bloqueados: set[tuple[int, int]] = set()
    agora_ = agora()
    pend = db.scalars(select(Outbox).where(Outbox.status == "pendente").order_by(Outbox.id)).all()
    for ob in pend:
        k = (ob.sistema_id, ob.tarefa_id)
        if k in bloqueados:
            continue
        if ob.proxima_tentativa > agora_:
            bloqueados.add(k)       # preserva a ordem: aguarda a anterior
            continue
        sistema = db.get(SistemaOrigem, ob.sistema_id)
        try:
            r = cliente.post(sistema.webhook_url, json=ob.payload, headers={"X-API-Key": sistema.webhook_key})
            if r.status_code >= 300:
                raise RuntimeError(f"HTTP {r.status_code}")
            ob.status, ob.enviado_em, ob.ultimo_erro = "enviado", agora(), ""
            ob.tentativas += 1
            enviados += 1
        except Exception as e:
            ob.tentativas += 1
            ob.ultimo_erro = str(e)[:300]
            ob.proxima_tentativa = agora() + timedelta(seconds=min(5 * 2 ** min(ob.tentativas, 6), 300))
            bloqueados.add(k)
            falhas += 1
        db.commit()
    return {"enviados": enviados, "falhas": falhas, "pendentes": len([o for o in pend if o.status == "pendente"])}


def forcar_agora(db: Session) -> None:
    """Zera o backoff (botão 'sincronizar agora')."""
    for ob in db.scalars(select(Outbox).where(Outbox.status == "pendente")):
        ob.proxima_tentativa = agora()
    db.commit()
