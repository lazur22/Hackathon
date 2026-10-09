"""OS digital, rotas por proximidade e assistente de suporte."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatConversa, Local, Participante, Tarefa, Usuario
from ..security import exige, tem_perfil, usuario_atual
from ..services import chatbot, geo, os_digital
from ..services.erros import ErroNegocio
from .tarefas import carregar

router = APIRouter(prefix="/api/v1", tags=["OS digital, rotas e assistente"])
ABERTOS = ("ATRIBUIDA", "EM_ANDAMENTO", "BLOQUEADA", "PENDENTE")


# ------------------------------------------------------------------ OS digital
@router.get("/tarefas/{tarefa_id}/os")
def os_da_tarefa(tarefa_id: int, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return os_digital.montar(db, carregar(db, tarefa_id, u))


# ------------------------------------------------------------------ rotas
def _local_dict(l: Local) -> dict:
    return {"id": l.id, "nome": l.nome, "endereco": l.endereco, "lat": l.lat, "lon": l.lon, "central": l.central}


@router.get("/locais")
def locais(u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return [_local_dict(l) for l in db.scalars(select(Local).where(Local.ativo.is_(True))).all()]


@router.get("/rota/proximas")
def proximas(lat: Optional[float] = None, lon: Optional[float] = None, de_tarefa: Optional[int] = None,
             u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    """Missões do executor ordenadas por proximidade a partir da posição atual (ou do local da OS que acabou de fechar)
    — para atender a próxima sem voltar à central."""
    base = None
    if de_tarefa:
        o = db.get(Tarefa, de_tarefa)
        base = geo.ponto(o) if o else None
    if not base and lat is not None and lon is not None:
        base = (lat, lon)
    c = geo.central(db)
    origem = "posição atual" if base else "central"
    if not base and c:
        base = (c.lat, c.lon)
    if not base:
        raise ErroNegocio("Sem posição de referência (permita a localização ou cadastre a central).", 422)
    ts = db.scalars(select(Tarefa).where(Tarefa.status.in_(ABERTOS), Tarefa.id.in_(
        select(Participante.tarefa_id).where(Participante.usuario_id == u.id, Participante.ativo.is_(True))))).all()
    seq = geo.rota_vizinho_mais_proximo(base, ts)
    sem_coord = [t for t in ts if not geo.ponto(t)]
    return {"origem": origem,
            "sequencia": [{"id": x["tarefa"].id, "titulo": x["tarefa"].titulo, "local": x["tarefa"].local or x["tarefa"].unidade_demandante,
                           "prioridade": x["tarefa"].prioridade, "status": x["tarefa"].status, "km": x["km"], "min": x["min"],
                           "lat": x["tarefa"].lat, "lon": x["tarefa"].lon} for x in seq],
            "sem_localizacao": [{"id": t.id, "titulo": t.titulo} for t in sem_coord],
            "dica": ("Vá direto para a próxima missão — não precisa voltar à central." if seq else "Nenhuma missão aberta com local conhecido.")}


@router.get("/rota/resumo")
def resumo_rotas(u: Usuario = Depends(exige("gestor", "atendente")), db: Session = Depends(get_db)):
    """Visão do gestor: mapa esquemático, sequência sugerida por técnico, economia estimada vs. 'voltar à central'
    e oportunidades (OS de técnicos diferentes a poucos km uma da outra)."""
    c = geo.central(db)
    if not c:
        raise ErroNegocio("Central não cadastrada.", 404)
    base = (c.lat, c.lon)
    ts = db.scalars(select(Tarefa).where(Tarefa.status.in_(ABERTOS + ("NOVA",)))).all()
    if u.setor_id and not tem_perfil(u, "admin"):
        ts = [t for t in ts if t.setor_id == u.setor_id]
    por: dict[int, list[Tarefa]] = {}
    nomes: dict[int, str] = {}
    for t in ts:
        for p in t.participantes:
            if p.ativo and p.papel == "principal":
                por.setdefault(p.usuario_id, []).append(t); nomes[p.usuario_id] = p.usuario.nome
    rotas = []
    for uid, lst in por.items():
        seq = geo.rota_vizinho_mais_proximo(base, lst)
        rotas.append({"usuario_id": uid, "tecnico": nomes[uid], "paradas": [{"id": x["tarefa"].id, "titulo": x["tarefa"].titulo, "km": x["km"],
                      "lat": x["tarefa"].lat, "lon": x["tarefa"].lon, "prioridade": x["tarefa"].prioridade} for x in seq]})
    com_pt = [t for t in ts if geo.ponto(t)]
    oportunidades = []
    for i, a in enumerate(com_pt):
        for b in com_pt[i + 1:]:
            ta = {p.usuario_id for p in a.participantes if p.ativo and p.papel == "principal"}
            tb = {p.usuario_id for p in b.participantes if p.ativo and p.papel == "principal"}
            d = geo.haversine(geo.ponto(a), geo.ponto(b))
            if d <= 3.0 and ta != tb and a.id != b.id:
                oportunidades.append({"a": {"id": a.id, "titulo": a.titulo}, "b": {"id": b.id, "titulo": b.titulo}, "km": round(d, 1),
                                      "sugestao": "Locais próximos com técnicos diferentes (ou sem técnico): avaliar atender na mesma saída."})
    oportunidades.sort(key=lambda x: x["km"])
    return {"central": _local_dict(c), "locais": [_local_dict(l) for l in db.scalars(select(Local).where(Local.ativo.is_(True), Local.central.is_(False))).all()],
            "rotas": rotas, "economia": geo.economia(base, {uid: lst for uid, lst in por.items()}), "oportunidades": oportunidades[:8],
            "sem_localizacao": [t.id for t in ts if not geo.ponto(t)],
            "aviso": "Coordenadas da demonstração são aproximadas/fictícias. Valores de economia são ESTIMATIVAS sobre os atendimentos abertos."}


# ------------------------------------------------------------------ assistente
class Pergunta(BaseModel):
    mensagem: str = Field(min_length=3, max_length=1000)
    local: str = ""


@router.post("/chat")
def perguntar(d: Pergunta, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    r = chatbot.responder(db, u.id, d.mensagem, d.local)
    db.commit()
    return r


class Feedback(BaseModel):
    resolveu: bool
    abriu_os: bool = False


@router.post("/chat/{conversa_id}/feedback")
def feedback(conversa_id: int, d: Feedback, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = db.get(ChatConversa, conversa_id)
    if not c or c.usuario_id != u.id:
        raise ErroNegocio("Conversa não encontrada.", 404)
    c.resolveu, c.abriu_os = d.resolveu, d.abriu_os or (not d.resolveu)
    db.commit()
    return {"ok": True}


@router.get("/chat/resumo")
def resumo_chat(u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    return chatbot.resumo(db)


class Conhecimento(BaseModel):
    titulo: str = Field(min_length=3)
    sintomas: str = ""
    passos: list[str] = Field(min_length=1)


@router.post("/chat/conhecimento", status_code=201)
def ensinar(d: Conhecimento, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    item = chatbot.adicionar_conhecimento(db, d.titulo, d.sintomas, d.passos)
    db.commit()
    return item
