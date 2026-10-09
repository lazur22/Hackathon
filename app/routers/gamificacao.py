from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PontoEvento, Periodo, Tarefa, Usuario
from ..security import exige, tem_perfil, usuario_atual
from ..services import gamification
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1/gamificacao", tags=["Gamificação"])


@router.get("/regras")
def ver_regras(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return {"regras": gamification.regras(db), "padrao": gamification.REGRAS_PADRAO}


class NovasRegras(BaseModel):
    regras: dict


@router.put("/regras")
def alterar_regras(d: NovasRegras, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    """Regras ajustáveis pelo gestor, sem alterar código. Vale para pontos FUTUROS; o ledger passado não é reescrito."""
    return {"regras": gamification.salvar_regras(db, d.regras)}


@router.get("/ranking")
def ranking(escopo: str = "individual", periodo_id: Optional[int] = None, setor_id: Optional[int] = None,
            acumulado: bool = False, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    if escopo not in ("individual", "equipe", "setor"):
        raise ErroNegocio("escopo deve ser individual, equipe ou setor.", 422)
    per = db.get(Periodo, periodo_id) if periodo_id else gamification.periodo_ativo(db)
    db.commit()
    return {"periodo": {"id": per.id, "nome": per.nome, "ativo": per.ativo} if not acumulado else
            {"id": None, "nome": "Todo o histórico", "ativo": False},
            "escopo": escopo, "itens": gamification.ranking(db, escopo, per.id, setor_id, acumulado)}


@router.get("/periodos")
def periodos(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    gamification.periodo_ativo(db)
    db.commit()
    return [{"id": p.id, "nome": p.nome, "ativo": p.ativo, "inicio": p.inicio.isoformat() + "Z",
             "fim": p.fim.isoformat() + "Z" if p.fim else None}
            for p in db.scalars(select(Periodo).order_by(Periodo.id.desc())).all()]


class Encerrar(BaseModel):
    nome_proximo: Optional[str] = None


@router.post("/periodos/encerrar")
def encerrar(d: Encerrar, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    """Reinicia o placar (manual). Também ocorre automaticamente na virada do mês quando periodo='mensal'."""
    novo = gamification.encerrar_periodo(db, d.nome_proximo)
    return {"novo_periodo": {"id": novo.id, "nome": novo.nome}, "historico_preservado": True}


@router.get("/eu")
def meu_perfil(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    p = gamification.perfil_gamer(db, u)
    db.commit()
    return p


@router.get("/pontos")
def extrato(usuario_id: Optional[int] = None, periodo_id: Optional[int] = None, limite: int = 50,
            u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Extrato transparente: cada ponto tem uma explicação. Executor vê só o próprio; gestor vê de todos."""
    alvo = usuario_id or u.id
    if alvo != u.id and not tem_perfil(u, "gestor"):
        raise ErroNegocio("Você só pode ver o seu próprio extrato.", 403)
    q = select(PontoEvento).where(PontoEvento.usuario_id == alvo).order_by(PontoEvento.id.desc()).limit(min(limite, 300))
    if periodo_id:
        q = q.where(PontoEvento.periodo_id == periodo_id)
    return [{"id": p.id, "tipo": p.tipo, "pontos": p.pontos, "explicacao": p.explicacao, "tarefa_id": p.tarefa_id,
             "periodo_id": p.periodo_id, "em": p.criado_em.isoformat() + "Z"} for p in db.scalars(q).all()]
