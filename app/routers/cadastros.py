"""Cadastros configuráveis: setores, equipes, tipos de tarefa (fluxos) e usuários — a plataforma é genérica (Requisito 1)."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Equipe, Setor, TipoTarefa, Usuario
from ..security import PERFIS, exige, hash_senha, usuario_atual
from ..serializers import usuario_dict
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1/cadastros", tags=["Cadastros"])


def _tipo(t: TipoTarefa) -> dict:
    return {"id": t.id, "nome": t.nome, "setor_id": t.setor_id, "setor": t.setor.nome,
            "equipe_padrao_id": t.equipe_padrao_id, "equipe_padrao": t.equipe_padrao.nome if t.equipe_padrao else None,
            "complexidade": t.complexidade, "sla_inicio_min": t.sla_inicio_min, "exige_evidencia": t.exige_evidencia,
            "exige_validacao": t.exige_validacao, "campos_obrigatorios": t.campos_obrigatorios or [], "ativo": t.ativo}


@router.get("/estrutura")
def estrutura(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Tudo o que os formulários precisam (setores, equipes, tipos)."""
    return {
        "setores": [{"id": s.id, "nome": s.nome, "sigla": s.sigla, "ativo": s.ativo} for s in db.scalars(select(Setor)).all()],
        "equipes": [{"id": e.id, "nome": e.nome, "setor_id": e.setor_id, "ativo": e.ativo} for e in db.scalars(select(Equipe)).all()],
        "tipos": [_tipo(t) for t in db.scalars(select(TipoTarefa)).all()],
    }


@router.get("/usuarios")
def usuarios(perfil: Optional[str] = None, u: Usuario = Depends(exige("gestor", "atendente")), db: Session = Depends(get_db)):
    todos = db.scalars(select(Usuario).where(Usuario.ativo.is_(True)).order_by(Usuario.nome)).all()
    return [usuario_dict(x) for x in todos if not perfil or perfil in x.lista_perfis]


class NovoSetor(BaseModel):
    nome: str = Field(min_length=2)
    sigla: str = ""


@router.post("/setores", status_code=201)
def criar_setor(d: NovoSetor, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    s = Setor(nome=d.nome.strip(), sigla=d.sigla)
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErroNegocio("Já existe um setor com esse nome.", 409)
    return {"id": s.id, "nome": s.nome}


class NovaEquipe(BaseModel):
    nome: str = Field(min_length=2)
    setor_id: int


@router.post("/equipes", status_code=201)
def criar_equipe(d: NovaEquipe, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    if not db.get(Setor, d.setor_id):
        raise ErroNegocio("Setor inexistente.", 422)
    e = Equipe(nome=d.nome.strip(), setor_id=d.setor_id)
    db.add(e)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErroNegocio("Esta equipe já existe no setor.", 409)
    return {"id": e.id, "nome": e.nome}


class NovoTipo(BaseModel):
    nome: str = Field(min_length=2)
    setor_id: int
    equipe_padrao_id: Optional[int] = None
    complexidade: str = "media"
    sla_inicio_min: int = 240
    exige_evidencia: bool = False
    exige_validacao: bool = True
    campos_obrigatorios: list[str] = []


@router.post("/tipos", status_code=201)
def criar_tipo(d: NovoTipo, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    if d.complexidade not in ("baixa", "media", "alta"):
        raise ErroNegocio("Complexidade deve ser baixa, media ou alta.", 422)
    t = TipoTarefa(**d.model_dump())
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErroNegocio("Tipo já existe neste setor ou referência inválida.", 409)
    db.refresh(t)
    return _tipo(t)


class AjusteTipo(BaseModel):
    complexidade: Optional[str] = None
    sla_inicio_min: Optional[int] = None
    exige_evidencia: Optional[bool] = None
    exige_validacao: Optional[bool] = None
    campos_obrigatorios: Optional[list[str]] = None
    equipe_padrao_id: Optional[int] = None
    ativo: Optional[bool] = None


@router.patch("/tipos/{tipo_id}")
def ajustar_tipo(tipo_id: int, d: AjusteTipo, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    t = db.get(TipoTarefa, tipo_id)
    if not t:
        raise ErroNegocio("Tipo não encontrado.", 404)
    for k, v in d.model_dump(exclude_none=True).items():
        if k == "complexidade" and v not in ("baixa", "media", "alta"):
            raise ErroNegocio("Complexidade inválida.", 422)
        setattr(t, k, v)
    db.commit()
    return _tipo(t)


class NovoUsuario(BaseModel):
    nome: str
    login: str
    senha: str = Field(min_length=6)
    perfis: list[str]
    equipe_id: Optional[int] = None
    setor_id: Optional[int] = None
    avatar: str = "🧭"
    contato: str = ""


@router.post("/usuarios", status_code=201)
def criar_usuario(d: NovoUsuario, u: Usuario = Depends(exige("admin")), db: Session = Depends(get_db)):
    ruins = [p for p in d.perfis if p not in PERFIS]
    if ruins or not d.perfis:
        raise ErroNegocio(f"Perfis válidos: {', '.join(PERFIS)}.", 422)
    novo = Usuario(nome=d.nome, login=d.login.strip().lower(), senha_hash=hash_senha(d.senha), perfis=",".join(d.perfis),
                   equipe_id=d.equipe_id, setor_id=d.setor_id, avatar=d.avatar, contato=d.contato)
    db.add(novo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ErroNegocio("Login já em uso.", 409)
    return usuario_dict(novo)
