"""Máquina de estados da jornada da demanda (Manual, seção 6).

NOVA ─atribuir→ ATRIBUIDA ─iniciar→ EM_ANDAMENTO ⇄ BLOQUEADA (impedimento / resolução pelo gestor)
EM_ANDAMENTO ─concluir→ CONCLUIDA_EXECUTOR ─validar(ok)→ RESOLVIDA
                                           └validar(não resolveu)→ PENDENTE ─atribuir→ ATRIBUIDA   (volta ao fluxo)

"Concluída pelo executor" e "resolvida pelo demandante" são estados DISTINTOS.
Toda transição grava um Evento (trilha de auditoria) e, se houver origem, uma mensagem na outbox.
"""
from __future__ import annotations
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Evento, Evidencia, Impedimento, Participante, SistemaOrigem, Tarefa, TipoTarefa, Usuario, agora,
                      Equipe)
from . import ai, gamification, outbox
from .erros import Duplicada, ErroNegocio
from .notify import notificar

ENCERRADOS = ("RESOLVIDA", "CANCELADA")
PRIORIDADES = ("baixa", "normal", "alta", "urgente")
TIPOS_IMPEDIMENTO = ("material", "terceiro", "acesso", "apoio", "divergencia", "outro")


# ------------------------------------------------------------------ utilitários
def registrar(db: Session, t: Tarefa, tipo: str, usuario: Optional[Usuario], texto: str = "", dados: dict | None = None,
              ator: str = "", evidencias: list[dict] | None = None, quando: Optional[datetime] = None,
              evento_origem: str | None = None, extra_outbox: dict | None = None) -> Evento:
    ev = Evento(tarefa_id=t.id, tipo=tipo, usuario_id=usuario.id if usuario else None,
                ator=(usuario.nome if usuario else ator or "sistema"), texto=texto, dados=dados or {},
                criado_em=quando or agora())
    db.add(ev)
    db.flush()
    for e in evidencias or []:
        db.add(Evidencia(tarefa_id=t.id, evento_id=ev.id, arquivo=e["arquivo"], nome_original=e.get("nome", ""),
                         mime=e.get("mime", "")))
    db.flush()
    db.refresh(t)
    if evento_origem:
        outbox.enfileirar(db, t, evento_origem, texto, ev.ator, extra_outbox)
    return ev


def eh_participante(t: Tarefa, u: Usuario, so_principal: bool = False) -> bool:
    return any(p.ativo and p.usuario_id == u.id and (not so_principal or p.papel == "principal")
               for p in t.participantes)


def _gestores_do_setor(db: Session, setor_id: int) -> list[Usuario]:
    todos = db.scalars(select(Usuario).where(Usuario.ativo.is_(True))).all()
    return [u for u in todos if ("gestor" in u.lista_perfis or "admin" in u.lista_perfis)
            and (u.setor_id in (None, setor_id))]


def _executores(t: Tarefa) -> list[Participante]:
    return [p for p in t.participantes if p.ativo]


def _exige_estado(t: Tarefa, *estados: str, acao: str) -> None:
    if t.status not in estados:
        raise ErroNegocio(f"Não é possível {acao} quando a tarefa está em {t.status}. "
                          f"Estados válidos: {', '.join(estados)}.", 409)


# ------------------------------------------------------------------ criação (atendente / integração)
def criar_tarefa(db: Session, *, titulo: str, descricao: str = "", setor_id: int, tipo_id: Optional[int] = None,
                 equipe_id: Optional[int] = None, local: str = "", unidade_demandante: str = "",
                 solicitante_nome: str = "", solicitante_contato: str = "", demandante_id: Optional[int] = None,
                 atendente: Optional[Usuario] = None, prioridade: Optional[str] = None,
                 origem: Optional[SistemaOrigem] = None, origem_id: Optional[str] = None, extra: Optional[dict] = None,
                 ator_texto: str = "", quando: Optional[datetime] = None, ia: bool = True) -> Tarefa:
    if not titulo.strip():
        raise ErroNegocio("Informe o título da demanda.", 422)
    if prioridade and prioridade not in PRIORIDADES:
        raise ErroNegocio(f"Prioridade inválida ({', '.join(PRIORIDADES)}).", 422)
    tipo = db.get(TipoTarefa, tipo_id) if tipo_id else None
    if tipo_id and not tipo:
        raise ErroNegocio("Tipo de tarefa inexistente.", 422)
    if origem and origem_id:
        existente = db.scalar(select(Tarefa).where(Tarefa.origem_sistema_id == origem.id, Tarefa.origem_id == str(origem_id)))
        if existente:
            raise Duplicada(existente)
    if tipo:
        valores = {"local": local, "ramal": solicitante_contato, "contato": solicitante_contato,
                   "descricao": descricao, "solicitante": solicitante_nome, "unidade": unidade_demandante}
        faltam = [c for c in (tipo.campos_obrigatorios or []) if not str(valores.get(c, (extra or {}).get(c, ""))).strip()]
        if faltam:
            raise ErroNegocio(f"Campos obrigatórios para '{tipo.nome}': {', '.join(faltam)}.", 422)
        equipe_id = equipe_id or tipo.equipe_padrao_id
    t = Tarefa(titulo=titulo.strip()[:200], descricao=descricao, setor_id=setor_id, tipo_id=tipo_id, equipe_id=equipe_id,
               local=local, unidade_demandante=unidade_demandante, solicitante_nome=solicitante_nome,
               solicitante_contato=solicitante_contato, demandante_id=demandante_id,
               atendente_id=atendente.id if atendente else None, prioridade=prioridade or "normal",
               complexidade=tipo.complexidade if tipo else "media", origem_sistema_id=origem.id if origem else None,
               origem_id=str(origem_id) if origem_id else None, extra=extra or {}, criado_em=quando or agora(),
               status="NOVA")
    db.add(t)
    db.flush()
    db.refresh(t)
    if ia:
        t.ia_sugestao = ai.analisar_demanda(db, t)
    registrar(db, t, "criada", atendente,
              f"Demanda registrada por {atendente.nome if atendente else (ator_texto or 'sistema de origem')}"
              + (f" (origem {origem.codigo} #{origem_id})" if origem else " diretamente na plataforma"),
              dados={"origem": origem.codigo if origem else None, "id_origem": origem_id},
              ator=ator_texto, quando=quando, evento_origem="recebida")
    for g in _gestores_do_setor(db, setor_id):
        notificar(db, g.id, "Nova tarefa para organizar", f"#{t.id} · {t.titulo}", t.id)
    return t


# ------------------------------------------------------------------ gestor
def atribuir(db: Session, t: Tarefa, gestor: Usuario, executor_ids: list[int], observacao: str = "",
             equipe_id: Optional[int] = None, prioridade: Optional[str] = None,
             quando: Optional[datetime] = None) -> Tarefa:
    _exige_estado(t, "NOVA", "PENDENTE", "ATRIBUIDA", "EM_ANDAMENTO", "BLOQUEADA", acao="atribuir")
    if not executor_ids:
        raise ErroNegocio("Selecione ao menos um executor.", 422)
    ids = list(dict.fromkeys(executor_ids))
    usuarios = [db.get(Usuario, i) for i in ids]
    for u in usuarios:
        if not u or not u.ativo or "executor" not in u.lista_perfis:
            raise ErroNegocio("Todos os atribuídos precisam ter o perfil de executor.", 422)
    if prioridade:
        if prioridade not in PRIORIDADES:
            raise ErroNegocio("Prioridade inválida.", 422)
        t.prioridade = prioridade
    if equipe_id:
        t.equipe_id = equipe_id
    existentes = {p.usuario_id: p for p in t.participantes}
    for i, uid in enumerate(ids):
        papel = "principal" if i == 0 else "apoio"
        if uid in existentes:
            existentes[uid].ativo, existentes[uid].papel = True, papel
        else:
            t.participantes.append(Participante(usuario_id=uid, papel=papel))
    for uid, p in existentes.items():
        if uid not in ids:
            p.ativo = False
    if t.status in ("NOVA", "PENDENTE", "ATRIBUIDA"):
        t.status = "ATRIBUIDA"
        t.atribuido_em = quando or agora()
    db.flush()
    db.refresh(t)
    nomes = ", ".join(u.nome for u in usuarios)
    registrar(db, t, "atribuida", gestor, f"Atribuída a {nomes}" + (f". Obs.: {observacao}" if observacao else ""),
              dados={"executores": ids, "principal": ids[0]}, quando=quando, evento_origem="encaminhada")
    for u in usuarios:
        notificar(db, u.id, "🎯 Nova missão!", f"#{t.id} · {t.titulo}"
                  + (f" — {t.local}" if t.local else ""), t.id)
    return t


def resolver_impedimento(db: Session, t: Tarefa, gestor: Usuario, resolucao: str, apoio_ids: list[int] | None = None,
                         quando: Optional[datetime] = None) -> Tarefa:
    _exige_estado(t, "BLOQUEADA", acao="resolver o impedimento")
    if len(resolucao.strip()) < 3:
        raise ErroNegocio("Descreva a providência tomada.", 422)
    now = quando or agora()
    for imp in t.impedimentos:
        if not imp.resolvido_em:
            imp.resolvido_em, imp.resolvido_por, imp.resolucao = now, gestor.id, resolucao
            t.bloqueada_min += int((now - imp.aberto_em).total_seconds() / 60)
    for uid in apoio_ids or []:
        u = db.get(Usuario, uid)
        if u and not eh_participante(t, u):
            t.participantes.append(Participante(usuario_id=uid, papel="apoio"))
    t.status = "EM_ANDAMENTO"
    db.flush()
    db.refresh(t)
    registrar(db, t, "impedimento_resolvido", gestor, f"Impedimento tratado: {resolucao}", quando=quando,
              dados={"apoio": apoio_ids or []}, evento_origem="andamento")
    for p in _executores(t):
        notificar(db, p.usuario_id, "✅ Impedimento resolvido", f"#{t.id} liberada para continuar", t.id)
    return t


def cancelar(db: Session, t: Tarefa, usuario: Usuario, motivo: str, quando=None) -> Tarefa:
    _exige_estado(t, "NOVA", "ATRIBUIDA", "EM_ANDAMENTO", "BLOQUEADA", "PENDENTE", "CONCLUIDA_EXECUTOR", acao="cancelar")
    if len(motivo.strip()) < 3:
        raise ErroNegocio("Informe o motivo do cancelamento.", 422)
    t.status, t.token_validacao = "CANCELADA", None
    registrar(db, t, "cancelada", usuario, f"Cancelada: {motivo}", quando=quando, evento_origem="cancelada")
    for p in _executores(t):
        notificar(db, p.usuario_id, "Missão cancelada", f"#{t.id} · {motivo}", t.id)
    return t


# ------------------------------------------------------------------ executor
def _exige_participante(t: Tarefa, u: Usuario) -> None:
    if not eh_participante(t, u):
        raise ErroNegocio("Esta missão não está atribuída a você.", 403)


def iniciar(db: Session, t: Tarefa, u: Usuario, lat: float | None = None, lon: float | None = None,
            quando: Optional[datetime] = None) -> Tarefa:
    _exige_participante(t, u)
    _exige_estado(t, "ATRIBUIDA", acao="iniciar o atendimento")
    t.status, t.iniciado_em = "EM_ANDAMENTO", quando or agora()
    dados = {"lat": lat, "lon": lon} if lat is not None and lon is not None else {}
    registrar(db, t, "iniciada", u, "Chegou ao local e iniciou o atendimento" if dados else "Iniciou o atendimento",
              dados=dados, quando=quando, evento_origem="andamento")
    if eh_participante(t, u, so_principal=True):
        gamification.ao_iniciar(db, t, u, quando)
    for g in _gestores_do_setor(db, t.setor_id):
        notificar(db, g.id, "▶ Atendimento iniciado", f"#{t.id} · {u.nome}", t.id)
    return t


def andamento(db: Session, t: Tarefa, u: Usuario, texto: str, evidencias: list[dict] | None = None,
              quando: Optional[datetime] = None) -> Tarefa:
    _exige_participante(t, u)
    _exige_estado(t, "EM_ANDAMENTO", "BLOQUEADA", acao="registrar andamento")
    if len(texto.strip()) < 2 and not evidencias:
        raise ErroNegocio("Escreva uma observação ou anexe uma evidência.", 422)
    registrar(db, t, "andamento", u, texto.strip(), evidencias=evidencias, quando=quando, evento_origem="andamento")
    return t


def registrar_impedimento(db: Session, t: Tarefa, u: Usuario, tipo: str, descricao: str,
                          evidencias: list[dict] | None = None, quando: Optional[datetime] = None) -> Tarefa:
    _exige_participante(t, u)
    _exige_estado(t, "EM_ANDAMENTO", acao="registrar impedimento")
    if tipo not in TIPOS_IMPEDIMENTO:
        raise ErroNegocio(f"Tipo de impedimento inválido ({', '.join(TIPOS_IMPEDIMENTO)}).", 422)
    if len(descricao.strip()) < 5:
        raise ErroNegocio("Descreva o impedimento.", 422)
    imp = Impedimento(tarefa_id=t.id, tipo=tipo, descricao=descricao.strip(), aberto_em=quando or agora(), aberto_por=u.id)
    t.impedimentos.append(imp)
    t.status = "BLOQUEADA"
    db.flush()
    sug = ai.sugerir_apoio(db, t, descricao)
    registrar(db, t, "impedimento", u, f"[{tipo}] {descricao.strip()}", dados={"tipo": tipo, "ia_apoio": sug},
              evidencias=evidencias, quando=quando, evento_origem="impedimento",
              extra_outbox={"impedimento": {"tipo": tipo, "descricao": descricao.strip()}})
    gamification.ao_impedimento(db, t, u, tipo, descricao, quando)
    for g in _gestores_do_setor(db, t.setor_id):
        notificar(db, g.id, "⛔ Impedimento na missão", f"#{t.id} · {tipo}: {descricao.strip()[:80]}", t.id)
    return t


def pedir_apoio(db: Session, t: Tarefa, u: Usuario, texto: str, quando: Optional[datetime] = None) -> Tarefa:
    _exige_participante(t, u)
    _exige_estado(t, "EM_ANDAMENTO", "BLOQUEADA", acao="pedir apoio")
    registrar(db, t, "apoio_solicitado", u, f"Pediu apoio: {texto}", quando=quando, evento_origem="andamento")
    for g in _gestores_do_setor(db, t.setor_id):
        notificar(db, g.id, "🤝 Apoio solicitado", f"#{t.id} · {u.nome}: {texto[:80]}", t.id)
    return t


def concluir(db: Session, t: Tarefa, u: Usuario, descricao: str, evidencias: list[dict] | None = None,
             quando: Optional[datetime] = None) -> Tarefa:
    _exige_participante(t, u)
    _exige_estado(t, "EM_ANDAMENTO", acao="concluir")
    if len(descricao.strip()) < 5:
        raise ErroNegocio("Descreva o que foi realizado.", 422)
    if t.tipo and t.tipo.exige_evidencia:
        ja_tem = any(ev.evidencias for ev in t.eventos) or bool(evidencias)
        if not ja_tem:
            raise ErroNegocio(f"O tipo '{t.tipo.nome}' exige ao menos uma evidência (foto/arquivo).", 422)
    t.status, t.concluido_exec_em = "CONCLUIDA_EXECUTOR", quando or agora()
    exige_val = t.tipo.exige_validacao if t.tipo else True
    dados = {}
    if exige_val:
        t.token_validacao = secrets.token_urlsafe(18)
        dados["validar_path"] = f"/validar/{t.token_validacao}"
    registrar(db, t, "concluida", u, descricao.strip(), dados=dados, evidencias=evidencias, quando=quando,
              evento_origem="executada")
    if eh_participante(t, u, so_principal=True):
        gamification.ao_concluir(db, t, u, quando)
    if exige_val:
        notificar(db, t.demandante_id, "Seu chamado foi atendido", f"#{t.id} · confirme se foi resolvido", t.id)
        for g in _gestores_do_setor(db, t.setor_id):
            notificar(db, g.id, "⏳ Aguardando confirmação do demandante", f"#{t.id} · {t.titulo}", t.id)
    else:
        validar(db, t, resolvido=True, nota=None, comentario="Tipo sem validação do demandante", por=None, quando=quando,
                ator="regra do tipo de tarefa", forcar=True)
    return t


# ------------------------------------------------------------------ demandante
def validar(db: Session, t: Tarefa, *, resolvido: bool, nota: Optional[int] = None, comentario: str = "",
            motivo_pendencia: str = "", por: Optional[Usuario] = None, ator: str = "",
            quando: Optional[datetime] = None, forcar: bool = False) -> Tarefa:
    _exige_estado(t, "CONCLUIDA_EXECUTOR", acao="validar")
    if resolvido:
        if not forcar and (nota is None or not (1 <= int(nota) <= 5)):
            raise ErroNegocio("Informe uma nota de 1 a 5 para o atendimento.", 422)
        t.status, t.resolvido_em = "RESOLVIDA", quando or agora()
        t.avaliacao, t.comentario_avaliacao = (int(nota) if nota else None), comentario or ""
        t.token_validacao = None
        registrar(db, t, "validada", por, f"Resolução confirmada. Nota {nota or '—'}. {comentario}".strip(),
                  dados={"resolvido": True, "nota": nota}, ator=ator or "demandante", quando=quando,
                  evento_origem="resolvida")
        gamification.ao_validar(db, t, True, nota, quando)
        for p in _executores(t):
            notificar(db, p.usuario_id, "🏆 Missão confirmada!", f"#{t.id} · nota {nota or '—'}", t.id)
    else:
        if len(motivo_pendencia.strip()) < 5:
            raise ErroNegocio("Explique o que ainda não foi resolvido.", 422)
        t.status, t.token_validacao = "PENDENTE", None
        t.reaberturas += 1
        registrar(db, t, "pendencia", por, f"Demandante informa que NÃO foi resolvido: {motivo_pendencia.strip()}",
                  dados={"resolvido": False}, ator=ator or "demandante", quando=quando, evento_origem="pendencia")
        gamification.ao_validar(db, t, False, None, quando)
        if t.atendente_id:
            notificar(db, t.atendente_id, "↩ Pendência do demandante", f"#{t.id} voltou para análise", t.id)
        for g in _gestores_do_setor(db, t.setor_id):
            notificar(db, g.id, "↩ Pendência: tarefa voltou ao fluxo", f"#{t.id} · {motivo_pendencia.strip()[:80]}", t.id)
        for p in _executores(t):
            notificar(db, p.usuario_id, "↩ Missão reaberta", f"#{t.id} · o demandante informou pendência", t.id)
    return t


# ------------------------------------------------------------------ IA com conferência humana
def decidir_sugestao_ia(db: Session, t: Tarefa, usuario: Usuario, aceitar: bool, campos: list[str] | None = None) -> Tarefa:
    """Sugestões da IA só mudam a tarefa quando um responsável as aceita (fica registrado)."""
    s = dict(t.ia_sugestao or {})
    if not s:
        raise ErroNegocio("Não há sugestão de IA para esta tarefa.", 404)
    if s.get("estado") != "pendente":
        raise ErroNegocio("Esta sugestão já foi conferida.", 409)
    aplicadas = []
    if aceitar:
        campos = campos or ["equipe", "prioridade", "tipo"]
        top = (s.get("classificacao") or [{}])[0]
        if "equipe" in campos and top.get("equipe_id"):
            t.equipe_id = top["equipe_id"]
            aplicadas.append("equipe")
        if "tipo" in campos and top.get("tipo_id"):
            t.tipo_id = top["tipo_id"]
            tipo = db.get(TipoTarefa, top["tipo_id"])
            if tipo:
                t.complexidade = tipo.complexidade
            aplicadas.append("tipo")
        if "prioridade" in campos and s.get("prioridade", {}).get("valor"):
            t.prioridade = s["prioridade"]["valor"]
            aplicadas.append("prioridade")
    s["estado"] = "aceita" if aceitar else "rejeitada"
    s["conferido_por"] = usuario.nome
    s["aplicadas"] = aplicadas
    t.ia_sugestao = s
    registrar(db, t, "ia_conferida", usuario,
              f"Sugestão da IA {'aceita' if aceitar else 'rejeitada'}" + (f" ({', '.join(aplicadas)})" if aplicadas else ""),
              dados={"aceitar": aceitar, "aplicadas": aplicadas})
    return t
