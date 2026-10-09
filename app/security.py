"""Autenticação por token de sessão e controle de acesso por perfil (Requisito 4). Somente biblioteca padrão."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .config import SESSAO_HORAS
from .db import get_db
from .models import Sessao, Usuario, agora

PERFIS = ("admin", "atendente", "gestor", "executor", "demandante")


def hash_senha(senha: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 120_000)
    return f"pbkdf2${salt.hex()}${h.hex()}"


def confere_senha(senha: str, armazenado: str) -> bool:
    try:
        _, salt, h = armazenado.split("$")
        novo = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 120_000)
        return hmac.compare_digest(novo.hex(), h)
    except Exception:
        return False


def criar_sessao(db: Session, usuario: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Sessao(token=token, usuario_id=usuario.id, expira_em=agora() + timedelta(hours=SESSAO_HORAS)))
    db.commit()
    return token


def usuario_atual(
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None, description="token via query (apenas SSE/EventSource)"),
    db: Session = Depends(get_db),
) -> Usuario:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif t:
        token = t
    if not token:
        raise HTTPException(401, "Não autenticado")
    s = db.get(Sessao, token)
    if not s or s.expira_em < agora():
        raise HTTPException(401, "Sessão expirada")
    u = db.get(Usuario, s.usuario_id)
    if not u or not u.ativo:
        raise HTTPException(401, "Usuário inativo")
    return u


def exige(*perfis: str):
    """Dependência: o usuário precisa ter ao menos um dos perfis (admin sempre passa)."""
    def _dep(u: Usuario = Depends(usuario_atual)) -> Usuario:
        meus = set(u.lista_perfis)
        if "admin" in meus or meus & set(perfis):
            return u
        raise HTTPException(403, f"Perfil sem permissão (necessário: {', '.join(perfis)})")
    return _dep


def tem_perfil(u: Usuario, *perfis: str) -> bool:
    meus = set(u.lista_perfis)
    return "admin" in meus or bool(meus & set(perfis))
