"""Ordem de Serviço digital: responde às perguntas da OS de papel — QUANDO, QUEM, COMO, O QUE FOI FEITO,
HÁ PENDÊNCIAS, HÁ FOTOS — e carrega um selo de integridade (hash da trilha) para rastreio e segurança."""
from __future__ import annotations
import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Local, Tarefa
from ..serializers import iso


def _min(a, b) -> Optional[float]:
    return round((b - a).total_seconds() / 60, 1) if a and b else None


def montar(db: Session, t: Tarefa) -> dict:
    eventos = sorted(t.eventos, key=lambda e: (e.criado_em, e.id))
    local = db.get(Local, t.local_id) if t.local_id else None
    criada = next((e for e in eventos if e.tipo == "criada"), None)
    concl = next((e for e in reversed(eventos) if e.tipo == "concluida"), None)
    valid = next((e for e in reversed(eventos) if e.tipo == "validada"), None)
    inicio = next((e for e in eventos if e.tipo == "iniciada"), None)
    execucao = [{"quando": iso(e.criado_em), "quem": e.ator, "o_que": e.texto, "tipo": e.tipo,
                 "fotos": len(e.evidencias)} for e in eventos if e.tipo in ("atribuida", "iniciada", "andamento", "apoio_solicitado", "impedimento", "impedimento_resolvido", "concluida", "pendencia", "validada")]
    pendencias = [{"origem": "impedimento", "descricao": i.descricao, "tipo": i.tipo, "aberta_em": iso(i.aberto_em),
                   "situacao": "resolvida" if i.resolvido_em else "ABERTA", "resolucao": i.resolucao, "resolvida_em": iso(i.resolvido_em)}
                  for i in t.impedimentos]
    for e in eventos:
        if e.tipo == "pendencia":
            pendencias.append({"origem": "demandante", "descricao": e.texto, "tipo": "nao_resolveu", "aberta_em": iso(e.criado_em),
                               "situacao": "registrada", "resolucao": "", "resolvida_em": None})
    fotos = [{"id": ev.id, "url": f"/api/v1/evidencias/{ev.id}", "nome": ev.nome_original, "mime": ev.mime,
              "quando": iso(ev.criado_em), "quem": e.ator} for e in eventos for ev in e.evidencias]
    corpo_selo = json.dumps([[e.id, e.tipo, e.ator, e.texto, iso(e.criado_em)] for e in eventos], ensure_ascii=False)
    selo = hashlib.sha256((f"{t.id}|{t.titulo}|" + corpo_selo).encode()).hexdigest()
    return {
        "numero": f"{t.criado_em.year}/{t.id:06d}", "id": t.id, "status": t.status, "natureza": "corretiva",
        "quando": {"aberta_em": iso(t.criado_em), "atribuida_em": iso(t.atribuido_em), "iniciada_em": iso(t.iniciado_em),
                   "concluida_em": iso(t.concluido_exec_em), "resolvida_em": iso(t.resolvido_em),
                   "tempo_ate_atendimento_min": _min(t.criado_em, t.iniciado_em), "tempo_de_reparo_min": _min(t.criado_em, t.concluido_exec_em),
                   "tempo_total_min": _min(t.criado_em, t.resolvido_em)},
        "quem": {"solicitante": t.solicitante_nome, "contato": t.solicitante_contato, "secretaria": t.secretaria,
                 "unidade": t.unidade_demandante, "local": t.local, "endereco": local.endereco if local else "",
                 "aberta_por": criada.ator if criada else "", "encaminhada_para": t.equipe.nome if t.equipe else "",
                 "executores": [{"nome": p.usuario.nome, "papel": p.papel} for p in t.participantes if p.ativo],
                 "confirmada_por": valid.ator if valid else ""},
        "equipamento": {"patrimonio": t.patrimonio, "descricao": t.equipamento},
        "problema": {"titulo": t.titulo, "descricao": t.descricao, "categoria": t.tipo.nome if t.tipo else "", "prioridade": t.prioridade},
        "como": execucao,
        "o_que_foi_feito": concl.texto if concl else "",
        "pendencias": pendencias, "tem_pendencia_aberta": any(p["situacao"] == "ABERTA" for p in pendencias) or t.status == "PENDENTE",
        "fotos": fotos,
        "localizacao_no_atendimento": inicio.dados if inicio and inicio.dados else None,
        "avaliacao": {"nota": t.avaliacao, "comentario": t.comentario_avaliacao}, "reaberturas": t.reaberturas,
        "origem": {"sistema": t.origem_sistema.codigo, "id": t.origem_id} if t.origem_sistema else None,
        "selo_integridade": selo,
        "qualidade_do_registro": _qualidade(t, concl, fotos),
    }


def _qualidade(t: Tarefa, concl, fotos) -> dict:
    """Quanto a OS está completa — o contrário do 'N/D' e do 'OS ok' do papel."""
    itens = {"patrimonio_informado": bool(t.patrimonio), "local_informado": bool(t.local), "contato_informado": bool(t.solicitante_contato),
             "descricao_do_servico": bool(concl and len(concl.texto.strip()) >= 20), "foto": bool(fotos), "confirmacao_do_demandante": bool(t.resolvido_em)}
    return {"itens": itens, "pontos": sum(itens.values()), "de": len(itens)}
