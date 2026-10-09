"""Indicadores (Manual, seção 16). Cada indicador informa O QUE MEDE e QUAIS REGISTROS usa no cálculo."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import mean, median
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import BASE_DIR
from ..db import get_db
from ..models import Evento, Impedimento, Participante, Tarefa, Usuario, agora
from ..security import exige
from ..services import ai
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1", tags=["Indicadores"])


def _min(a, b):
    return (b - a).total_seconds() / 60 if a and b else None


def _fmt(v, nd=1):
    return round(v, nd) if v is not None else None


@router.get("/indicadores")
def indicadores(dias: int = 90, setor_id: Optional[int] = None, u: Usuario = Depends(exige("gestor")),
                db: Session = Depends(get_db)):
    desde = agora() - timedelta(days=dias)
    q = select(Tarefa).where(Tarefa.criado_em >= desde)
    if setor_id:
        q = q.where(Tarefa.setor_id == setor_id)
    elif u.setor_id:
        q = q.where(Tarefa.setor_id == u.setor_id)
    ts = db.scalars(q).all()

    por_status = Counter(t.status for t in ts)
    espera_inicio = [m for t in ts if (m := _min(t.atribuido_em, t.iniciado_em)) is not None]
    execucao = [m for t in ts if (m := _min(t.iniciado_em, t.concluido_exec_em)) is not None]
    confirmacao = [m for t in ts if (m := _min(t.concluido_exec_em, t.resolvido_em)) is not None]
    ciclo = [m for t in ts if (m := _min(t.criado_em, t.resolvido_em)) is not None]
    notas = [t.avaliacao for t in ts if t.avaliacao]
    ids = [t.id for t in ts]
    imps = db.scalars(select(Impedimento).where(Impedimento.tarefa_id.in_(ids))).all() if ids else []
    motivos = Counter(i.tipo for i in imps)
    colab = db.scalars(select(Participante).where(Participante.tarefa_id.in_(ids), Participante.papel == "apoio")).all() if ids else []
    ativos = db.scalars(select(Participante.usuario_id).where(Participante.tarefa_id.in_(ids))).all() if ids else []

    semanas: dict[str, dict] = defaultdict(lambda: {"abertas": 0, "resolvidas": 0})
    for t in ts:
        semanas[f"{t.criado_em.isocalendar().year}-S{t.criado_em.isocalendar().week:02d}"]["abertas"] += 1
        if t.resolvido_em:
            r = t.resolvido_em
            semanas[f"{r.isocalendar().year}-S{r.isocalendar().week:02d}"]["resolvidas"] += 1

    return {
        "janela_dias": dias, "total": len(ts),
        "indicadores": [
            {"id": "volume", "nome": "Tarefas por situação", "valor": dict(por_status),
             "mede": "Quantas tarefas estão recebidas (NOVA/ATRIBUIDA), em execução (EM_ANDAMENTO/BLOQUEADA), aguardando confirmação e resolvidas.",
             "fonte": "Campo `status` de cada tarefa criada na janela."},
            {"id": "tempo_inicio", "nome": "Tempo até iniciar o atendimento (min)", "mediana": _fmt(median(espera_inicio)) if espera_inicio else None,
             "media": _fmt(mean(espera_inicio)) if espera_inicio else None, "amostra": len(espera_inicio),
             "mede": "Do momento da atribuição até o executor tocar em 'Iniciar'.", "fonte": "`atribuido_em` → `iniciado_em`."},
            {"id": "tempo_execucao", "nome": "Tempo de execução (min)", "mediana": _fmt(median(execucao)) if execucao else None,
             "media": _fmt(mean(execucao)) if execucao else None, "amostra": len(execucao),
             "mede": "Do início do atendimento até o executor informar a conclusão (inclui tempo bloqueada).",
             "fonte": "`iniciado_em` → `concluido_exec_em`."},
            {"id": "tempo_confirmacao", "nome": "Tempo até a confirmação do demandante (min)", "mediana": _fmt(median(confirmacao)) if confirmacao else None,
             "amostra": len(confirmacao), "mede": "Da conclusão informada pelo executor até a resolução confirmada.",
             "fonte": "`concluido_exec_em` → `resolvido_em`."},
            {"id": "ciclo", "nome": "Ciclo completo (min)", "mediana": _fmt(median(ciclo)) if ciclo else None, "amostra": len(ciclo),
             "mede": "Da abertura da demanda até a resolução confirmada.", "fonte": "`criado_em` → `resolvido_em`."},
            {"id": "bloqueios", "nome": "Impedimentos e principais motivos", "valor": dict(motivos), "total": len(imps),
             "tarefas_bloqueadas_agora": por_status.get("BLOQUEADA", 0),
             "mede": "Quantos impedimentos foram registrados e por qual causa.", "fonte": "Tabela `impedimentos` (tipo)."},
            {"id": "pendencias", "nome": "Pendências / reaberturas", "valor": sum(t.reaberturas for t in ts),
             "taxa": _fmt(100 * sum(1 for t in ts if t.reaberturas) / len(ts)) if ts else None,
             "mede": "Vezes em que o demandante indicou que a entrega não resolveu (e % de tarefas afetadas).",
             "fonte": "Campo `reaberturas` e eventos `pendencia`."},
            {"id": "satisfacao", "nome": "Satisfação dos demandantes (1–5)", "media": _fmt(mean(notas), 2) if notas else None,
             "amostra": len(notas), "mede": "Média das notas dadas na validação.", "fonte": "Campo `avaliacao`."},
            {"id": "colaboracao", "nome": "Participação e colaboração", "executores_ativos": len(set(ativos)),
             "participacoes_como_apoio": len(colab),
             "mede": "Quantos servidores atuaram e quantas vezes houve apoio entre colegas/equipes.",
             "fonte": "Tabela `participantes` (papel principal/apoio)."},
        ],
        "evolucao_semanal": [{"semana": k, **v} for k, v in sorted(semanas.items())],
        "bloqueadas": [{"id": t.id, "titulo": t.titulo} for t in ts if t.status == "BLOQUEADA"],
    }


@router.get("/indicadores/baseline")
def baseline(u: Usuario = Depends(exige("gestor"))):
    """Linha de base do Help Desk real (2026), agregada e SEM dados pessoais — antes da plataforma."""
    p = BASE_DIR / "data" / "baseline_helpdesk.json"
    if not p.exists():
        raise ErroNegocio("Baseline não gerada (rode scripts/gerar_baseline.py).", 404)
    return json.loads(p.read_text())


@router.get("/ia/impedimentos-recorrentes")
def recorrentes(setor_id: Optional[int] = None, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    return {"itens": ai.impedimentos_recorrentes(db, setor_id),
            "como_funciona": "Agrupa os impedimentos por tipo e extrai termos frequentes das descrições (contagem local, sem LLM)."}
