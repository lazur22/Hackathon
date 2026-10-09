from __future__ import annotations
from typing import Optional

from .config import BASE_URL
from .models import Tarefa, Usuario
from .security import tem_perfil
from .services.outbox import iso, LEGADO
from .services.workflow import ENCERRADOS, eh_participante


def usuario_dict(u: Usuario) -> dict:
    return {"id": u.id, "nome": u.nome, "login": u.login, "perfis": u.lista_perfis, "avatar": u.avatar,
            "equipe_id": u.equipe_id, "equipe": u.equipe.nome if u.equipe else None, "setor_id": u.setor_id,
            "contato": u.contato}


def acoes_permitidas(t: Tarefa, u: Usuario) -> list[str]:
    """Quais ações o usuário pode executar agora (a UI só mostra estes botões; a API valida de novo)."""
    a = []
    gestor = tem_perfil(u, "gestor")
    if gestor and t.status not in ("RESOLVIDA", "CANCELADA", "CONCLUIDA_EXECUTOR"):
        a.append("atribuir")
    if gestor and t.status == "BLOQUEADA":
        a.append("resolver_impedimento")
    if (gestor or tem_perfil(u, "atendente")) and t.status in ("NOVA", "ATRIBUIDA", "EM_ANDAMENTO", "BLOQUEADA", "PENDENTE", "CONCLUIDA_EXECUTOR"):
        a.append("cancelar")
    if gestor and (t.ia_sugestao or {}).get("estado") == "pendente":
        a.append("conferir_ia")
    if tem_perfil(u, "executor") and eh_participante(t, u):
        if t.status == "ATRIBUIDA":
            a.append("iniciar")
        if t.status in ("EM_ANDAMENTO", "BLOQUEADA"):
            a.append("andamento")
        if t.status == "EM_ANDAMENTO":
            a += ["impedimento", "apoio", "concluir"]
    if t.status == "CONCLUIDA_EXECUTOR" and t.demandante_id == u.id:
        a.append("validar")
    return a


def tarefa_resumo(t: Tarefa) -> dict:
    principal = next((p for p in t.participantes if p.ativo and p.papel == "principal"), None)
    return {
        "id": t.id, "titulo": t.titulo, "status": t.status, "prioridade": t.prioridade, "complexidade": t.complexidade,
        "setor": t.setor.nome if t.setor else None, "setor_id": t.setor_id,
        "equipe": t.equipe.nome if t.equipe else None, "equipe_id": t.equipe_id,
        "tipo": t.tipo.nome if t.tipo else None, "local": t.local, "unidade": t.unidade_demandante,
        "solicitante": t.solicitante_nome,
        "executor": principal.usuario.nome if principal else None,
        "executores": [{"id": p.usuario_id, "nome": p.usuario.nome, "papel": p.papel, "avatar": p.usuario.avatar}
                       for p in t.participantes if p.ativo],
        "origem": ({"sistema": t.origem_sistema.codigo, "nome": t.origem_sistema.nome, "id": t.origem_id}
                   if t.origem_sistema else None),
        "status_legado": LEGADO.get(t.status),
        "criado_em": iso(t.criado_em), "atribuido_em": iso(t.atribuido_em), "iniciado_em": iso(t.iniciado_em),
        "concluido_exec_em": iso(t.concluido_exec_em), "resolvido_em": iso(t.resolvido_em),
        "avaliacao": t.avaliacao, "reaberturas": t.reaberturas,
        "ia_pendente": (t.ia_sugestao or {}).get("estado") == "pendente",
    }


def tarefa_detalhe(t: Tarefa, u: Usuario, incluir_validacao: bool = True) -> dict:
    d = tarefa_resumo(t)
    d.update({
        "descricao": t.descricao, "solicitante_contato": t.solicitante_contato, "demandante_id": t.demandante_id,
        "comentario_avaliacao": t.comentario_avaliacao, "bloqueada_min": t.bloqueada_min,
        "ia_sugestao": t.ia_sugestao,
        "impedimentos": [{"id": i.id, "tipo": i.tipo, "descricao": i.descricao, "aberto_em": iso(i.aberto_em),
                          "resolvido_em": iso(i.resolvido_em), "resolucao": i.resolucao} for i in t.impedimentos],
        "eventos": [{"id": e.id, "tipo": e.tipo, "ator": e.ator, "texto": e.texto, "criado_em": iso(e.criado_em),
                     "dados": {k: v for k, v in (e.dados or {}).items() if k != "validar_path"},
                     "evidencias": [{"id": ev.id, "nome": ev.nome_original, "mime": ev.mime,
                                     "url": f"/api/v1/evidencias/{ev.id}"} for ev in e.evidencias]} for e in t.eventos],
        "acoes": acoes_permitidas(t, u),
    })
    # link de validação para o ATENDENTE/GESTOR repassar ao demandante (telefone, WhatsApp institucional, e-mail…)
    if incluir_validacao and t.token_validacao and tem_perfil(u, "gestor", "atendente"):
        d["link_validacao"] = f"{BASE_URL}/validar/{t.token_validacao}"
    return d
