from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Sessao, Usuario
from ..security import confere_senha, criar_sessao, usuario_atual
from ..serializers import usuario_dict
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticação"])


class Login(BaseModel):
    login: str
    senha: str


@router.post("/login")
def login(dados: Login, db: Session = Depends(get_db)):
    u = db.scalar(select(Usuario).where(Usuario.login == dados.login.strip().lower()))
    if not u or not u.ativo or not confere_senha(dados.senha, u.senha_hash):
        raise ErroNegocio("Usuário ou senha inválidos.", 401)
    return {"token": criar_sessao(db, u), "usuario": usuario_dict(u)}


@router.get("/eu")
def eu(u: Usuario = Depends(usuario_atual)):
    return usuario_dict(u)


@router.post("/sair")
def sair(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    db.execute(delete(Sessao).where(Sessao.usuario_id == u.id))
    db.commit()
    return {"ok": True}
