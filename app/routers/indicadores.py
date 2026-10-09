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


# ------------------------------------------------------------------ confiabilidade: MTTR, MTBF, recorrência, avaliações
def _chave_ativo(t: Tarefa) -> Optional[str]:
    """'Ativo' = onde o problema ocorre. Preferência: patrimônio (etiqueta); senão local cadastrado; senão texto do local."""
    if t.patrimonio:
        return f"pat:{t.patrimonio}"
    if t.local_id:
        return f"loc:{t.local_id}"
    loc = ai._norm(t.local or "").strip()
    return f"txt:{loc}" if loc and "informado na ligacao" not in loc else None


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@router.get("/indicadores/confiabilidade")
def confiabilidade(dias: int = 180, u: Usuario = Depends(exige("gestor")), db: Session = Depends(get_db)):
    from ..services import chatbot
    agora_ = agora()
    q = select(Tarefa).where(Tarefa.criado_em >= agora_ - timedelta(days=dias))
    if u.setor_id:
        q = q.where(Tarefa.setor_id == u.setor_id)
    ts = sorted(db.scalars(q).all(), key=lambda t: t.criado_em)

    # --- OS abertas em X tempo
    def abertas(d0, d1):
        return sum(1 for t in ts if agora_ - timedelta(days=d0) <= t.criado_em < agora_ - timedelta(days=d1))
    a7, a30, ant30 = abertas(7, 0), abertas(30, 0), abertas(60, 30)
    diario = Counter(t.criado_em.strftime("%Y-%m-%d") for t in ts if t.criado_em >= agora_ - timedelta(days=30))

    # --- MTTR: da abertura até o serviço restabelecido (concluído pelo executor); horas
    reparo = [(t, _min(t.criado_em, t.concluido_exec_em) / 60) for t in ts if t.concluido_exec_em]
    mttr_h = [h for _, h in reparo]
    ativo_h = [_min(t.iniciado_em, t.concluido_exec_em) / 60 for t in ts if t.iniciado_em and t.concluido_exec_em]
    por_tipo = defaultdict(list)
    for t, h in reparo:
        por_tipo[t.tipo.nome if t.tipo else "—"].append(h)

    # --- MTBF: por ativo (patrimônio/local), tempo médio entre falhas consecutivas; dias
    # (chave inclui o tipo: falhas de natureza diferente no mesmo local não contam como a mesma falha)
    por_ativo: dict[tuple, list[Tarefa]] = defaultdict(list)
    for t in ts:
        k = _chave_ativo(t)
        if k:
            por_ativo[(k, t.tipo_id)].append(t)
    lista_mtbf, intervalos = [], []
    for (k, _tipo), g in por_ativo.items():
        if len(g) < 2:
            continue
        iv = [(b.criado_em - a.criado_em).total_seconds() / 86400 for a, b in zip(g, g[1:])]
        intervalos += iv
        lista_mtbf.append({"ativo": (g[-1].unidade_demandante or g[-1].local or k), "tipo": g[-1].tipo.nome if g[-1].tipo else "—",
                           "falhas": len(g), "mtbf_dias": round(mean(iv), 1), "ultima_falha": g[-1].criado_em.isoformat() + "Z",
                           "os": [x.id for x in g]})
    lista_mtbf.sort(key=lambda x: x["mtbf_dias"])

    # --- recorrência: mesma descrição/necessidade (similaridade) no mesmo ativo/unidade, ou reabertura
    toks = {t.id: set(ai.tokens(f"{t.titulo} {t.descricao}")) for t in ts}
    recorrentes, pares = set(), []
    for i, b in enumerate(ts):
        for a in ts[:i]:
            if (b.criado_em - a.criado_em).days > 60:
                continue
            mesmo_lugar = (_chave_ativo(a) == _chave_ativo(b) and _chave_ativo(a)) or (a.unidade_demandante and a.unidade_demandante == b.unidade_demandante)
            if mesmo_lugar and _jaccard(toks[a.id], toks[b.id]) >= 0.25:
                recorrentes.add(b.id); pares.append((a, b))
                break
    top = Counter()
    exemplos = {}
    for a, b in pares:
        k = (b.unidade_demandante or b.local, b.tipo.nome if b.tipo else "—")
        top[k] += 1; exemplos.setdefault(k, []).append(b.id)
    reabertas = sum(1 for t in ts if t.reaberturas)
    recorrencia = {"taxa_percentual": round(100 * len(recorrentes) / len(ts), 1) if ts else 0, "os_recorrentes": len(recorrentes),
                   "os_reabertas": reabertas,
                   "ranking": [{"onde": k[0], "tipo": k[1], "repeticoes": n, "os": exemplos[k][:6],
                                "acao": "Investigar causa-raiz (troca de equipamento/cabo/contrato) em vez de novo reparo."}
                               for k, n in top.most_common(6)]}

    # --- avaliações
    notas = [t.avaliacao for t in ts if t.avaliacao]
    por_eq = defaultdict(list)
    for t in ts:
        if t.avaliacao and t.equipe:
            por_eq[t.equipe.nome].append(t.avaliacao)

    return {
        "janela_dias": dias, "total": len(ts),
        "os_abertas": {"ultimos_7_dias": a7, "ultimos_30_dias": a30, "30_dias_anteriores": ant30,
                       "variacao_percentual": round(100 * (a30 - ant30) / ant30, 1) if ant30 else None,
                       "por_dia_30d": [{"dia": d, "n": n} for d, n in sorted(diario.items())],
                       "mede": "Quantidade de OS abertas por período (volume de demanda).", "fonte": "`criado_em` de cada OS."},
        "mttr": {"horas_media": round(mean(mttr_h), 1) if mttr_h else None, "horas_mediana": round(median(mttr_h), 1) if mttr_h else None,
                 "horas_so_execucao_media": round(mean(ativo_h), 1) if ativo_h else None, "amostra": len(mttr_h),
                 "por_tipo": sorted([{"tipo": k, "horas_media": round(mean(v), 1), "n": len(v)} for k, v in por_tipo.items()], key=lambda x: -x["horas_media"])[:6],
                 "mede": "MTTR = tempo médio de reparo: da abertura da OS até o serviço restabelecido (conclusão informada pelo técnico).",
                 "fonte": "`criado_em` → `concluido_exec_em`."},
        "mtbf": {"dias_media": round(mean(intervalos), 1) if intervalos else None, "ativos_com_reincidencia": len(lista_mtbf),
                 "piores": lista_mtbf[:6],
                 "mede": "MTBF = tempo médio entre falhas do mesmo ativo (patrimônio ou local) e da mesma natureza. Quanto maior, melhor.",
                 "fonte": "Intervalo entre `criado_em` de OS consecutivas do mesmo ativo/local e tipo. Precisa de histórico longo para ser confiável."},
        "recorrencia": {**recorrencia, "mede": "OS que repetem descrição/necessidade no mesmo local nos 60 dias seguintes a outra OS, e OS reabertas.",
                        "fonte": "Similaridade de texto (Jaccard ≥ 0,25) + mesmo ativo/unidade."},
        "avaliacoes": {"media": round(mean(notas), 2) if notas else None, "amostra": len(notas),
                       "distribuicao": {str(n): notas.count(n) for n in range(1, 6)},
                       "percentual_4_ou_5": round(100 * sum(1 for n in notas if n >= 4) / len(notas), 1) if notas else None,
                       "por_equipe": sorted([{"equipe": k, "media": round(mean(v), 2), "n": len(v)} for k, v in por_eq.items()], key=lambda x: -x["media"]),
                       "mede": "Nota (1–5) dada pelo solicitante ao confirmar o atendimento.", "fonte": "Campo `avaliacao`."},
        "assistente": chatbot.resumo(db, 90),
    }
