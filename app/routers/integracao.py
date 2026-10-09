"""Integração bidirecional com sistemas de origem (Requisito 2).

ENTRADA  POST /api/v1/integracao/tarefas      (X-API-Key do sistema de origem; idempotente por id_origem)
CONSULTA GET  /api/v1/integracao/tarefas/{id_origem}   (alternativa de polling para sistemas sem webhook)
SAÍDA    outbox -> POST {webhook_url} do sistema (ver services/outbox.py): andamento, impedimentos, conclusão e validação.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Equipe, Outbox, Setor, SistemaOrigem, Tarefa, TipoTarefa, Usuario
from ..security import exige
from ..serializers import tarefa_resumo
from ..services import outbox, workflow
from ..services.erros import Duplicada, ErroNegocio

router = APIRouter(prefix="/api/v1/integracao", tags=["Integração"])


def sistema_por_chave(x_api_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> SistemaOrigem:
    s = db.scalar(select(SistemaOrigem).where(SistemaOrigem.api_key == (x_api_key or "-"), SistemaOrigem.ativo.is_(True)))
    if not s:
        raise ErroNegocio("Chave de API inválida.", 401)
    return s


class Solicitante(BaseModel):
    nome: str = ""
    contato: str = ""
    login: Optional[str] = None


class TarefaEntrada(BaseModel):
    id_origem: str = Field(min_length=1, description="ID do chamado no sistema de origem (chave de idempotência)")
    titulo: str = Field(min_length=3)
    descricao: str = ""
    setor: Optional[str] = None
    tipo: Optional[str] = None
    equipe: Optional[str] = None
    unidade: str = ""
    local: str = ""
    solicitante: Solicitante = Solicitante()
    atendente: str = ""
    prioridade: Optional[str] = None
    aberto_em: Optional[datetime] = None
    patrimonio: str = ""          # etiqueta do equipamento (campo 'Etiqueta' da OS)
    equipamento: str = ""
    secretaria: str = ""
    extra: dict = {}


@router.post("/tarefas", status_code=201)
def receber(d: TarefaEntrada, s: SistemaOrigem = Depends(sistema_por_chave), db: Session = Depends(get_db)):
    setor = db.scalar(select(Setor).where(func.lower(Setor.nome) == (d.setor or "").lower())) if d.setor else None
    setor_id = setor.id if setor else s.setor_padrao_id
    if not setor_id:
        raise ErroNegocio("Setor não informado e o sistema de origem não tem setor padrão.", 422)
    tipo = db.scalar(select(TipoTarefa).where(func.lower(TipoTarefa.nome) == (d.tipo or "").lower())) if d.tipo else None
    equipe = db.scalar(select(Equipe).where(func.lower(Equipe.nome) == (d.equipe or "").lower())) if d.equipe else None
    demandante = None
    if d.solicitante.login:
        demandante = db.scalar(select(Usuario).where(Usuario.login == d.solicitante.login.lower()))
    elif d.solicitante.nome:
        demandante = db.scalar(select(Usuario).where(func.lower(Usuario.nome) == d.solicitante.nome.lower()))
    try:
        t = workflow.criar_tarefa(
            db, titulo=d.titulo, descricao=d.descricao, setor_id=setor_id, tipo_id=tipo.id if tipo else None,
            equipe_id=equipe.id if equipe else None, local=d.local, unidade_demandante=d.unidade,
            solicitante_nome=d.solicitante.nome, solicitante_contato=d.solicitante.contato,
            demandante_id=demandante.id if demandante and "demandante" in demandante.lista_perfis else None,
            prioridade=d.prioridade, origem=s, origem_id=d.id_origem, extra=d.extra,
            patrimonio=d.patrimonio, equipamento=d.equipamento, secretaria=d.secretaria,
            ator_texto=f"atendente {d.atendente}" if d.atendente else "", quando=None)
    except Duplicada as dup:
        # Reenvio do mesmo chamado: devolve o registro existente (200), sem criar duplicata.
        return _resposta(dup.tarefa, duplicada=True)
    db.commit()
    return _resposta(t, duplicada=False)


def _resposta(t: Tarefa, duplicada: bool) -> dict:
    return {"id_plataforma": t.id, "id_origem": t.origem_id, "status": t.status, "duplicada": duplicada}


@router.get("/tarefas/{id_origem}")
def consultar(id_origem: str, s: SistemaOrigem = Depends(sistema_por_chave), db: Session = Depends(get_db)):
    t = db.scalar(select(Tarefa).where(Tarefa.origem_sistema_id == s.id, Tarefa.origem_id == id_origem))
    if not t:
        raise ErroNegocio("Chamado não encontrado.", 404)
    return {**tarefa_resumo(t), "validacao": {"nota": t.avaliacao, "comentario": t.comentario_avaliacao}}


# ------------------------------------------------------------------ painel de integração (gestor)
@router.get("/sistemas")
def sistemas(u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    out = []
    for s in db.scalars(select(SistemaOrigem)).all():
        pend = db.scalar(select(func.count()).select_from(Outbox).where(Outbox.sistema_id == s.id, Outbox.status == "pendente"))
        env = db.scalar(select(func.count()).select_from(Outbox).where(Outbox.sistema_id == s.id, Outbox.status == "enviado"))
        n = db.scalar(select(func.count()).select_from(Tarefa).where(Tarefa.origem_sistema_id == s.id))
        out.append({"id": s.id, "codigo": s.codigo, "nome": s.nome, "webhook_url": s.webhook_url, "ativo": s.ativo,
                    "tarefas_recebidas": n, "mensagens_enviadas": env, "mensagens_pendentes": pend})
    return out


@router.get("/outbox")
def ver_outbox(status: Optional[str] = None, limite: int = 60, u: Usuario = Depends(exige("gestor")),
               db: Session = Depends(get_db)):
    q = select(Outbox).order_by(Outbox.id.desc()).limit(min(limite, 300))
    if status:
        q = q.where(Outbox.status == status)
    return [{"id": o.id, "tarefa_id": o.tarefa_id, "chave": o.chave, "status": o.status, "tentativas": o.tentativas,
             "ultimo_erro": o.ultimo_erro, "evento": o.payload.get("evento"), "status_legado": o.payload.get("status_legado"),
             "criado_em": outbox.iso(o.criado_em), "enviado_em": outbox.iso(o.enviado_em),
             "proxima_tentativa": outbox.iso(o.proxima_tentativa) if o.status == "pendente" else None}
            for o in db.scalars(q).all()]


@router.post("/sincronizar")
def sincronizar(u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    outbox.forcar_agora(db)
    return outbox.processar(db)
