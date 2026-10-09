"""Gamificação configurável (Requisito 5).

Princípios (respondem ao Manual do Desafio, seção 9):
* O placar mede QUALIDADE, COMPLEXIDADE e COLABORAÇÃO — não só entrega.
* Pontos nascem em duas etapas: parte na conclusão (executor) e o restante só após a VALIDAÇÃO do demandante,
  multiplicado pela nota. Assim a avaliação de quem pediu o serviço influencia diretamente a pontuação.
* Tarefa bloqueada por fator externo (material, terceiro, acesso) não é punida: registrar o impedimento com
  justificativa gera pontos, o relógio de SLA é congelado e uma reabertura posterior é isenta de penalidade.
* Tudo é regra em dados (tabela `config`), editável pelo gestor, sem alterar código.
* Placar periódico: encerrar o período abre outro; o ledger (`pontos`) é permanente, então o histórico é preservado.
* XP e nível usam o ledger inteiro (não zeram); o ranking usa o período.
"""
from __future__ import annotations
import copy
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Config, Conquista, Equipe, Evento, Participante, PontoEvento, Periodo, Tarefa, Usuario, agora)

REGRAS_PADRAO: dict = {
    "pontos_base": 100,
    "complexidade": {"baixa": 1.0, "media": 1.5, "alta": 2.5},
    "fracao_na_conclusao": 0.4,                  # parcela liberada quando o executor conclui
    "qualidade_por_nota": {"1": 0.0, "2": 0.4, "3": 0.7, "4": 1.0, "5": 1.2},   # multiplica a parcela restante
    "bonus_sla": {"ativo": True, "pontos": 15},  # iniciar dentro do SLA do tipo de tarefa
    "colaboracao": {"pontos_apoio": 30},         # por tarefa em que atuou como apoio/co-executor
    "impedimento": {"pontos_registro_justificado": 10, "isenta_penalidade": True,
                    "tipos_externos": ["material", "terceiro", "acesso", "apoio"]},
    "reabertura": {"penalidade": -20},           # pendência indicada pelo demandante
    "periodo": "mensal",                         # mensal | manual
    "niveis": [
        {"nivel": 1, "nome": "Aprendiz", "xp": 0},
        {"nivel": 2, "nome": "Explorador", "xp": 200},
        {"nivel": 3, "nome": "Técnico", "xp": 600},
        {"nivel": 4, "nome": "Veterano", "xp": 1500},
        {"nivel": 5, "nome": "Mestre da Cidade", "xp": 3000},
    ],
}

CONQUISTAS = {
    "PRIMEIRA_MISSAO": ("Primeira missão", "Teve a primeira missão resolvida e confirmada.", "🏁"),
    "DEZ_MISSOES": ("Dez missões", "10 missões resolvidas e confirmadas.", "🔟"),
    "COLABORADOR": ("Colaborador", "Atuou como apoio em 3 missões.", "🤝"),
    "QUALIDADE_TOP": ("Qualidade top", "Média ≥ 4,5 em pelo menos 5 avaliações.", "⭐"),
    "CACADOR_IMPEDIMENTOS": ("Caçador de impedimentos", "Registrou 3 impedimentos com justificativa.", "🔎"),
    "VELOZ": ("Veloz", "Iniciou 5 missões dentro do SLA.", "⚡"),
}


def regras(db: Session) -> dict:
    c = db.get(Config, "gamificacao")
    base = copy.deepcopy(REGRAS_PADRAO)
    if c:
        _merge(base, c.valor)
    return base


def _merge(base: dict, novo: dict) -> None:
    for k, v in novo.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def salvar_regras(db: Session, novas: dict) -> dict:
    atual = regras(db)
    _validar(novas)
    _merge(atual, novas)
    c = db.get(Config, "gamificacao")
    if c:
        c.valor = atual
    else:
        db.add(Config(chave="gamificacao", valor=atual))
    db.commit()
    return atual


def _validar(n: dict) -> None:
    from ..services.erros import ErroNegocio
    if "pontos_base" in n and not (0 <= float(n["pontos_base"]) <= 10_000):
        raise ErroNegocio("pontos_base fora do intervalo 0–10000", 422)
    if "fracao_na_conclusao" in n and not (0 <= float(n["fracao_na_conclusao"]) <= 1):
        raise ErroNegocio("fracao_na_conclusao deve estar entre 0 e 1", 422)
    if "periodo" in n and n["periodo"] not in ("mensal", "manual"):
        raise ErroNegocio("periodo deve ser 'mensal' ou 'manual'", 422)


# ------------------------------------------------------------------ períodos
def _nome_mes(d: datetime) -> str:
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro"]
    return f"{meses[d.month - 1].capitalize()}/{d.year}"


def periodo_ativo(db: Session, quando: Optional[datetime] = None) -> Periodo:
    """Retorna o período ativo; em modo mensal, vira o mês automaticamente (sem apagar nada)."""
    quando = quando or agora()
    p = db.scalar(select(Periodo).where(Periodo.ativo.is_(True)).order_by(Periodo.id.desc()))
    modo = regras(db)["periodo"]
    if p and modo == "mensal" and (p.inicio.year, p.inicio.month) != (quando.year, quando.month) and quando > p.inicio:
        p.ativo, p.fim = False, quando.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        p = None
    if not p:
        inicio = quando.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if modo == "mensal" else quando
        p = Periodo(nome=_nome_mes(quando) if modo == "mensal" else f"Período de {quando:%d/%m/%Y}",
                    inicio=inicio, ativo=True)
        db.add(p)
        db.flush()
    return p


def encerrar_periodo(db: Session, nome_proximo: Optional[str] = None) -> Periodo:
    """Reinício manual do placar. O período antigo continua consultável; os pontos NÃO são apagados."""
    p = periodo_ativo(db)
    p.ativo, p.fim = False, agora()
    novo = Periodo(nome=nome_proximo or f"Período de {agora():%d/%m/%Y %H:%M}", inicio=agora(), ativo=True)
    db.add(novo)
    db.commit()
    return novo


# ------------------------------------------------------------------ ledger
def lancar(db: Session, usuario_id: int, tipo: str, pontos: float, tarefa: Optional[Tarefa], explicacao: str,
           quando: Optional[datetime] = None) -> PontoEvento:
    u = db.get(Usuario, usuario_id)
    per = periodo_ativo(db, quando)
    pe = PontoEvento(usuario_id=usuario_id, equipe_id=u.equipe_id, setor_id=u.setor_id,
                     tarefa_id=tarefa.id if tarefa else None, periodo_id=per.id, tipo=tipo,
                     pontos=round(pontos, 1), explicacao=explicacao[:300], criado_em=quando or agora())
    db.add(pe)
    return pe


def _valor_tarefa(db: Session, t: Tarefa) -> float:
    r = regras(db)
    return r["pontos_base"] * r["complexidade"].get(t.complexidade, 1.0)


def _principal(t: Tarefa) -> Optional[Participante]:
    return next((p for p in t.participantes if p.ativo and p.papel == "principal"), None)


def _equipe_de(t: Tarefa) -> list[Participante]:
    return [p for p in t.participantes if p.ativo]


# ------------------------------------------------------------------ gatilhos do fluxo
def ao_iniciar(db: Session, t: Tarefa, u: Usuario, quando: Optional[datetime] = None) -> None:
    r = regras(db)
    if not r["bonus_sla"]["ativo"] or not t.tipo or not t.atribuido_em:
        return
    espera_min = ((quando or agora()) - t.atribuido_em).total_seconds() / 60 - t.bloqueada_min
    if espera_min <= t.tipo.sla_inicio_min:
        lancar(db, u.id, "sla", r["bonus_sla"]["pontos"], t,
               f"Início dentro do SLA ({int(espera_min)} min ≤ {t.tipo.sla_inicio_min} min)", quando)


def ao_impedimento(db: Session, t: Tarefa, u: Usuario, tipo: str, descricao: str, quando=None) -> None:
    r = regras(db)["impedimento"]
    if tipo in r["tipos_externos"] and len(descricao.strip()) >= 15:
        lancar(db, u.id, "impedimento", r["pontos_registro_justificado"], t,
               f"Impedimento externo ({tipo}) registrado com justificativa — sem penalidade de prazo", quando)
        verificar_conquistas(db, u)


def ao_concluir(db: Session, t: Tarefa, u: Usuario, quando=None) -> None:
    r = regras(db)
    parcela = _valor_tarefa(db, t) * r["fracao_na_conclusao"]
    lancar(db, u.id, "conclusao", parcela, t,
           f"Conclusão informada ({int(r['fracao_na_conclusao'] * 100)}% de {int(_valor_tarefa(db, t))} pts — "
           f"complexidade {t.complexidade}); o restante depende da confirmação do demandante", quando)


def ao_validar(db: Session, t: Tarefa, resolvido: bool, nota: Optional[int], quando=None) -> None:
    r = regras(db)
    principal = _principal(t)
    if resolvido:
        restante = _valor_tarefa(db, t) * (1 - r["fracao_na_conclusao"])
        fator = r["qualidade_por_nota"].get(str(nota), 1.0) if nota else 1.0
        if principal:
            lancar(db, principal.usuario_id, "validacao", restante * fator, t,
                   f"Resolução confirmada pelo demandante (nota {nota or '—'}, fator de qualidade ×{fator})", quando)
        for p in _equipe_de(t):
            if p.papel == "apoio":
                lancar(db, p.usuario_id, "colaboracao", r["colaboracao"]["pontos_apoio"], t,
                       "Colaboração: atuou como apoio em missão resolvida", quando)
        for p in _equipe_de(t):
            verificar_conquistas(db, p.usuario)
    else:
        isento = False
        if r["impedimento"]["isenta_penalidade"]:
            isento = any(i.tipo in r["impedimento"]["tipos_externos"] for i in t.impedimentos)
        if principal and not isento:
            lancar(db, principal.usuario_id, "reabertura", r["reabertura"]["penalidade"], t,
                   "Pendência indicada pelo demandante: a entrega não resolveu a necessidade", quando)
        elif principal and isento:
            lancar(db, principal.usuario_id, "reabertura", 0, t,
                   "Pendência indicada, mas houve impedimento externo registrado: sem penalidade", quando)


# ------------------------------------------------------------------ conquistas / perfil / ranking
def verificar_conquistas(db: Session, u: Usuario) -> list[str]:
    novas = []

    def dar(codigo: str):
        if not db.scalar(select(Conquista).where(Conquista.usuario_id == u.id, Conquista.codigo == codigo)):
            db.add(Conquista(usuario_id=u.id, codigo=codigo))
            novas.append(codigo)

    resolvidas = db.scalar(select(func.count(func.distinct(PontoEvento.tarefa_id)))
                           .where(PontoEvento.usuario_id == u.id, PontoEvento.tipo == "validacao")) or 0
    if resolvidas >= 1:
        dar("PRIMEIRA_MISSAO")
    if resolvidas >= 10:
        dar("DEZ_MISSOES")
    if (db.scalar(select(func.count()).select_from(PontoEvento)
                  .where(PontoEvento.usuario_id == u.id, PontoEvento.tipo == "colaboracao")) or 0) >= 3:
        dar("COLABORADOR")
    if (db.scalar(select(func.count()).select_from(PontoEvento)
                  .where(PontoEvento.usuario_id == u.id, PontoEvento.tipo == "impedimento")) or 0) >= 3:
        dar("CACADOR_IMPEDIMENTOS")
    if (db.scalar(select(func.count()).select_from(PontoEvento)
                  .where(PontoEvento.usuario_id == u.id, PontoEvento.tipo == "sla")) or 0) >= 5:
        dar("VELOZ")
    notas = db.execute(
        select(Tarefa.avaliacao).join(PontoEvento, PontoEvento.tarefa_id == Tarefa.id)
        .where(PontoEvento.usuario_id == u.id, PontoEvento.tipo == "validacao", Tarefa.avaliacao.is_not(None))
    ).scalars().all()
    if len(notas) >= 5 and sum(notas) / len(notas) >= 4.5:
        dar("QUALIDADE_TOP")
    if novas:
        db.flush()
    return novas


def xp_total(db: Session, usuario_id: int) -> float:
    return max(0.0, db.scalar(select(func.coalesce(func.sum(PontoEvento.pontos), 0.0))
                              .where(PontoEvento.usuario_id == usuario_id)) or 0.0)


def nivel_de(db: Session, xp: float) -> dict:
    niveis = regras(db)["niveis"]
    atual = niveis[0]
    for n in niveis:
        if xp >= n["xp"]:
            atual = n
    prox = next((n for n in niveis if n["xp"] > atual["xp"]), None)
    return {"nivel": atual["nivel"], "nome": atual["nome"], "xp": round(xp),
            "proximo_xp": prox["xp"] if prox else None, "proximo_nome": prox["nome"] if prox else None,
            "progresso": (min(1.0, (xp - atual["xp"]) / (prox["xp"] - atual["xp"])) if prox else 1.0)}


def perfil_gamer(db: Session, u: Usuario) -> dict:
    per = periodo_ativo(db)
    pts_periodo = db.scalar(select(func.coalesce(func.sum(PontoEvento.pontos), 0.0))
                            .where(PontoEvento.usuario_id == u.id, PontoEvento.periodo_id == per.id)) or 0.0
    conq = db.scalars(select(Conquista).where(Conquista.usuario_id == u.id)).all()
    rk = ranking(db, "individual", per.id)
    pos = next((i + 1 for i, x in enumerate(rk) if x["id"] == u.id), None)
    return {
        "usuario": {"id": u.id, "nome": u.nome, "avatar": u.avatar},
        "periodo": {"id": per.id, "nome": per.nome},
        "pontos_periodo": round(pts_periodo, 1), "posicao": pos,
        "nivel": nivel_de(db, xp_total(db, u.id)),
        "conquistas": [{"codigo": c.codigo, "nome": CONQUISTAS[c.codigo][0], "descricao": CONQUISTAS[c.codigo][1],
                        "icone": CONQUISTAS[c.codigo][2], "em": c.concedida_em.isoformat() + "Z"} for c in conq],
        "catalogo_conquistas": [{"codigo": k, "nome": v[0], "descricao": v[1], "icone": v[2],
                                 "obtida": any(c.codigo == k for c in conq)} for k, v in CONQUISTAS.items()],
    }


def ranking(db: Session, escopo: str = "individual", periodo_id: Optional[int] = None, setor_id: Optional[int] = None,
            acumulado: bool = False) -> list[dict]:
    """escopo: individual | equipe | setor. periodo_id=None => período ativo. acumulado=True => todo o histórico."""
    q = select(PontoEvento)
    if not acumulado:
        q = q.where(PontoEvento.periodo_id == (periodo_id or periodo_ativo(db).id))
    if setor_id:
        q = q.where(PontoEvento.setor_id == setor_id)
    pontos = db.scalars(q).all()
    agg: dict[int, dict] = {}
    if escopo == "individual":
        for p in pontos:
            u = db.get(Usuario, p.usuario_id)
            a = agg.setdefault(u.id, {"id": u.id, "nome": u.nome, "avatar": u.avatar, "pontos": 0.0, "missoes": set(),
                                      "equipe": u.equipe.nome if u.equipe else ""})
            a["pontos"] += p.pontos
            if p.tarefa_id and p.tipo == "validacao":
                a["missoes"].add(p.tarefa_id)
    else:
        for p in pontos:
            if escopo == "equipe":
                eid = p.equipe_id or 0
                nome = db.get(Equipe, eid).nome if eid else "Sem equipe"
                chave = eid
            else:
                chave = p.setor_id or 0
                from ..models import Setor
                nome = db.get(Setor, chave).nome if chave else "Sem setor"
            a = agg.setdefault(chave, {"id": chave, "nome": nome, "avatar": "👥", "pontos": 0.0, "missoes": set(),
                                       "membros": set()})
            a["pontos"] += p.pontos
            a["membros"].add(p.usuario_id)
            if p.tarefa_id and p.tipo == "validacao":
                a["missoes"].add(p.tarefa_id)
    saida = []
    for a in agg.values():
        a["pontos"] = round(a["pontos"], 1)
        a["missoes"] = len(a["missoes"])
        if "membros" in a:
            a["membros"] = len(a["membros"])
        saida.append(a)
    saida.sort(key=lambda x: (-x["pontos"], x["nome"]))
    for i, a in enumerate(saida):
        a["posicao"] = i + 1
    return saida
