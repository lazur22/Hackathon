"""Validação pelo demandante via link com token (sem login): confirma, avalia ou indica pendência.

Decisão de projeto: o cadastro da demanda continua exclusivo do atendente (Manual, seção 3). O demandante só participa
da ETAPA DE VALIDAÇÃO — o link é o seu "ingresso", de uso único, expira ao validar.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import Evidencia, Tarefa
from ..services import workflow
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1/validar", tags=["Validação do demandante"])


def _por_token(db: Session, token: str) -> Tarefa:
    t = db.scalar(select(Tarefa).where(Tarefa.token_validacao == token))
    if not t or t.status != "CONCLUIDA_EXECUTOR":
        raise ErroNegocio("Este link de confirmação já foi usado ou expirou.", 404)
    return t


@router.get("/{token}")
def ver(token: str, db: Session = Depends(get_db)):
    t = _por_token(db, token)
    concl = next((e for e in reversed(t.eventos) if e.tipo == "concluida"), None)
    return {
        "id": t.id, "titulo": t.titulo, "descricao": t.descricao, "local": t.local, "unidade": t.unidade_demandante,
        "solicitante": t.solicitante_nome,
        "executores": [p.usuario.nome for p in t.participantes if p.ativo],
        "entrega": concl.texto if concl else "",
        "evidencias": [{"id": ev.id, "nome": ev.nome_original, "url": f"/api/v1/validar/{token}/evidencia/{ev.id}"}
                       for ev in (concl.evidencias if concl else [])],
        "reaberturas": t.reaberturas,
    }


class Resposta(BaseModel):
    resolvido: bool
    nota: Optional[int] = None
    comentario: str = ""
    motivo_pendencia: str = ""


@router.post("/{token}")
def responder(token: str, d: Resposta, db: Session = Depends(get_db)):
    t = _por_token(db, token)
    workflow.validar(db, t, resolvido=d.resolvido, nota=d.nota, comentario=d.comentario,
                     motivo_pendencia=d.motivo_pendencia, ator=f"demandante {t.solicitante_nome}".strip())
    db.commit()
    return {"ok": True, "status": t.status,
            "mensagem": "Obrigado! Sua confirmação foi registrada." if d.resolvido
            else "Registramos a pendência. O atendimento vai analisar e retornar."}


@router.get("/{token}/evidencia/{evidencia_id}")
def evidencia(token: str, evidencia_id: int, db: Session = Depends(get_db)):
    t = _por_token(db, token)
    ev = db.get(Evidencia, evidencia_id)
    if not ev or ev.tarefa_id != t.id:
        raise ErroNegocio("Evidência não encontrada.", 404)
    return FileResponse(Path(UPLOAD_DIR) / ev.arquivo, media_type=ev.mime or "application/octet-stream")
