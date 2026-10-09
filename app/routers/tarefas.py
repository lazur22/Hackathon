"""Tarefas: criação por atendente, atribuição pelo gestor, execução pelo executor, validação pelo demandante."""
from __future__ import annotations
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import Evidencia, Participante, Tarefa, Usuario
from ..security import exige, tem_perfil, usuario_atual
from ..serializers import tarefa_detalhe, tarefa_resumo
from ..services import chatbot, ai, workflow
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1", tags=["Tarefas"])

MIME_OK = ("image/", "application/pdf", "text/plain")
MAX_BYTES = 10 * 1024 * 1024


# ------------------------------------------------------------------ acesso
def _visivel(db: Session, t: Tarefa, u: Usuario) -> bool:
    if tem_perfil(u, "admin"):
        return True
    if tem_perfil(u, "gestor", "atendente") and (u.setor_id in (None, t.setor_id)):
        return True
    if tem_perfil(u, "executor") and workflow.eh_participante(t, u):
        return True
    if tem_perfil(u, "demandante") and t.demandante_id == u.id:
        return True
    return False


def carregar(db: Session, tarefa_id: int, u: Usuario) -> Tarefa:
    t = db.get(Tarefa, tarefa_id)
    if not t or not _visivel(db, t, u):
        raise ErroNegocio("Tarefa não encontrada.", 404)
    return t


async def _salvar(tarefa_id: int, arquivos: list[UploadFile]) -> list[dict]:
    saida = []
    for f in arquivos or []:
        if not f or not f.filename:
            continue
        if not (f.content_type or "").startswith(MIME_OK):
            raise ErroNegocio(f"Tipo de arquivo não permitido: {f.content_type}. Use imagem, PDF ou texto.", 415)
        dados = await f.read()
        if len(dados) > MAX_BYTES:
            raise ErroNegocio("Arquivo acima de 10 MB.", 413)
        pasta = Path(UPLOAD_DIR) / str(tarefa_id)
        pasta.mkdir(parents=True, exist_ok=True)
        seguro = re.sub(r"[^A-Za-z0-9._-]", "_", f.filename)[-80:]
        nome = f"{uuid.uuid4().hex[:10]}_{seguro}"
        (pasta / nome).write_bytes(dados)
        saida.append({"arquivo": f"{tarefa_id}/{nome}", "nome": f.filename, "mime": f.content_type})
    return saida


# ------------------------------------------------------------------ listagens
@router.get("/tarefas")
def listar(status: Optional[str] = None, setor_id: Optional[int] = None, equipe_id: Optional[int] = None,
           q: Optional[str] = None, limite: int = 200, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    consulta = select(Tarefa).order_by(Tarefa.id.desc())
    if not tem_perfil(u, "admin"):
        filtros = []
        if tem_perfil(u, "gestor", "atendente"):
            filtros.append(Tarefa.setor_id == u.setor_id if u.setor_id else Tarefa.id > 0)
        if tem_perfil(u, "executor"):
            filtros.append(Tarefa.id.in_(select(Participante.tarefa_id).where(Participante.usuario_id == u.id,
                                                                              Participante.ativo.is_(True))))
        if tem_perfil(u, "demandante"):
            filtros.append(Tarefa.demandante_id == u.id)
        if not filtros:
            return []
        consulta = consulta.where(or_(*filtros))
    if status:
        consulta = consulta.where(Tarefa.status.in_(status.split(",")))
    if setor_id:
        consulta = consulta.where(Tarefa.setor_id == setor_id)
    if equipe_id:
        consulta = consulta.where(Tarefa.equipe_id == equipe_id)
    if q:
        like = f"%{q}%"
        consulta = consulta.where(or_(Tarefa.titulo.ilike(like), Tarefa.descricao.ilike(like), Tarefa.local.ilike(like),
                                      Tarefa.origem_id == q))
    return [tarefa_resumo(t) for t in db.scalars(consulta.limit(min(limite, 500))).all()]


@router.get("/tarefas/{tarefa_id}")
def detalhe(tarefa_id: int, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return tarefa_detalhe(carregar(db, tarefa_id, u), u)


# ------------------------------------------------------------------ atendente
class NovaTarefa(BaseModel):
    titulo: str = Field(min_length=3)
    descricao: str = ""
    setor_id: int
    tipo_id: Optional[int] = None
    equipe_id: Optional[int] = None
    local: str = ""
    unidade_demandante: str = ""
    solicitante_nome: str = ""
    solicitante_contato: str = ""
    demandante_id: Optional[int] = None
    prioridade: Optional[str] = None
    patrimonio: str = ""
    equipamento: str = ""
    secretaria: str = ""


@router.post("/tarefas", status_code=201)
def criar(d: NovaTarefa, u: Usuario = Depends(exige("atendente", "gestor")), db: Session = Depends(get_db)):
    """Cadastro direto na plataforma (setor sem sistema próprio). Só atendente/gestor — nunca o solicitante."""
    t = workflow.criar_tarefa(db, atendente=u, **d.model_dump())
    db.commit()
    return tarefa_detalhe(t, u)


class Analise(BaseModel):
    titulo: str = ""
    descricao: str = ""
    unidade_demandante: str = ""
    local: str = ""
    solicitante_contato: str = ""


@router.post("/ia/analisar")
def analisar_previa(d: Analise, u: Usuario = Depends(exige("atendente", "gestor")), db: Session = Depends(get_db)):
    """Prévia enquanto o atendente digita: classificação, prioridade e perguntas para completar o chamado."""
    fake = Tarefa(titulo=d.titulo, descricao=d.descricao, unidade_demandante=d.unidade_demandante, local=d.local,
                  solicitante_contato=d.solicitante_contato, setor_id=0)
    r = ai.classificar(db, f"{d.titulo}. {d.descricao}", d.unidade_demandante)
    top = r["classificacao"][0]["categoria"] if r["classificacao"] else None
    r["lacunas"] = ai.lacunas(fake, top)
    r["similares"] = chatbot.similares(db, f"{d.titulo} {d.descricao}", 3)
    return r


# ------------------------------------------------------------------ gestor
class Atribuicao(BaseModel):
    executor_ids: list[int]
    observacao: str = ""
    equipe_id: Optional[int] = None
    prioridade: Optional[str] = None


@router.post("/tarefas/{tarefa_id}/atribuir")
def atribuir(tarefa_id: int, d: Atribuicao, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.atribuir(db, t, u, d.executor_ids, d.observacao, d.equipe_id, d.prioridade)
    db.commit()
    return tarefa_detalhe(t, u)


class ResolucaoImp(BaseModel):
    resolucao: str
    apoio_ids: list[int] = []


@router.post("/tarefas/{tarefa_id}/impedimento/resolver")
def resolver_imp(tarefa_id: int, d: ResolucaoImp, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.resolver_impedimento(db, t, u, d.resolucao, d.apoio_ids)
    db.commit()
    return tarefa_detalhe(t, u)


class Cancelamento(BaseModel):
    motivo: str


@router.post("/tarefas/{tarefa_id}/cancelar")
def cancelar(tarefa_id: int, d: Cancelamento, u: Usuario = Depends(exige("gestor", "atendente")),
             db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.cancelar(db, t, u, d.motivo)
    db.commit()
    return tarefa_detalhe(t, u)


class DecisaoIA(BaseModel):
    aceitar: bool
    campos: Optional[list[str]] = None


@router.post("/tarefas/{tarefa_id}/ia/decidir")
def decidir_ia(tarefa_id: int, d: DecisaoIA, u: Usuario = Depends(exige("gestor", "atendente")),
               db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.decidir_sugestao_ia(db, t, u, d.aceitar, d.campos)
    db.commit()
    return tarefa_detalhe(t, u)


@router.get("/tarefas/{tarefa_id}/ia/resumo")
def resumo_ia(tarefa_id: int, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    if tem_perfil(u, "demandante") and not tem_perfil(u, "gestor", "atendente", "executor"):
        raise ErroNegocio("Sem permissão para o resumo interno.", 403)
    return ai.resumir(t)


# ------------------------------------------------------------------ executor (mobile)
class Inicio(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None


@router.post("/tarefas/{tarefa_id}/iniciar")
def iniciar(tarefa_id: int, d: Inicio, u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.iniciar(db, t, u, d.lat, d.lon)
    db.commit()
    return tarefa_detalhe(t, u)


@router.post("/tarefas/{tarefa_id}/andamento")
async def andamento(tarefa_id: int, texto: str = Form(""), arquivos: list[UploadFile] = File(default=[]),
                    u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    ev = await _salvar(tarefa_id, arquivos)
    workflow.andamento(db, t, u, texto, ev)
    db.commit()
    return tarefa_detalhe(t, u)


@router.post("/tarefas/{tarefa_id}/impedimento")
async def impedimento(tarefa_id: int, tipo: str = Form(...), descricao: str = Form(...),
                      arquivos: list[UploadFile] = File(default=[]),
                      u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    ev = await _salvar(tarefa_id, arquivos)
    workflow.registrar_impedimento(db, t, u, tipo, descricao, ev)
    db.commit()
    return tarefa_detalhe(t, u)


class Apoio(BaseModel):
    texto: str


@router.post("/tarefas/{tarefa_id}/apoio")
def apoio(tarefa_id: int, d: Apoio, u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    workflow.pedir_apoio(db, t, u, d.texto)
    db.commit()
    return tarefa_detalhe(t, u)


@router.post("/tarefas/{tarefa_id}/concluir")
async def concluir(tarefa_id: int, descricao: str = Form(...), arquivos: list[UploadFile] = File(default=[]),
                   u: Usuario = Depends(exige("executor")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    ev = await _salvar(tarefa_id, arquivos)
    workflow.concluir(db, t, u, descricao, ev)
    db.commit()
    return tarefa_detalhe(t, u)


# ------------------------------------------------------------------ demandante autenticado
class Validacao(BaseModel):
    resolvido: bool
    nota: Optional[int] = None
    comentario: str = ""
    motivo_pendencia: str = ""


@router.post("/tarefas/{tarefa_id}/validar")
def validar(tarefa_id: int, d: Validacao, u: Usuario = Depends(exige("demandante")), db: Session = Depends(get_db)):
    t = carregar(db, tarefa_id, u)
    if t.demandante_id != u.id and not tem_perfil(u, "admin"):
        raise ErroNegocio("Somente o demandante desta tarefa pode validá-la.", 403)
    workflow.validar(db, t, resolvido=d.resolvido, nota=d.nota, comentario=d.comentario,
                     motivo_pendencia=d.motivo_pendencia, por=u)
    db.commit()
    return tarefa_detalhe(t, u)


# ------------------------------------------------------------------ evidências
@router.get("/evidencias/{evidencia_id}")
def baixar(evidencia_id: int, u: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    ev = db.get(Evidencia, evidencia_id)
    if not ev:
        raise ErroNegocio("Evidência não encontrada.", 404)
    carregar(db, ev.tarefa_id, u)  # mesma regra de visibilidade da tarefa
    caminho = Path(UPLOAD_DIR) / ev.arquivo
    if not caminho.exists():
        raise ErroNegocio("Arquivo indisponível.", 404)
    return FileResponse(caminho, media_type=ev.mime or "application/octet-stream", filename=ev.nome_original)
