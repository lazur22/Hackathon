"""Assistente de suporte (chatbot) 100% local. Funciona por RECUPERAÇÃO (TF-IDF + cosseno) sobre:
  1) base de conhecimento (procedimentos cadastrados) e
  2) as próprias OS já resolvidas (problema + o que foi feito). Cada OS nova concluída entra no índice sozinha
     => o assistente "fica mais esperto" a cada atendimento (retroalimentação). Feedback 👍/👎 reforça as fontes úteis.
Sem LLM obrigatório: se OLLAMA_URL existir, ele apenas REDIGE a resposta usando só o contexto recuperado."""
from __future__ import annotations
import math
from collections import Counter
from datetime import timedelta
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import OLLAMA_MODEL, OLLAMA_URL
from ..models import ChatConversa, Config, Tarefa, agora
from . import ai

LIMIAR = 0.28          # abaixo disso, o assistente admite que não sabe e sugere abrir OS

# Procedimentos-padrão (exemplo; o gestor adiciona mais pela tela de IA). categoria -> (sintomas, passos)
KB_BASE = [
    {"id": "kb-telefone", "titulo": "Telefone mudo / sem tom de linha",
     "sintomas": "telefone mudo sem tom de linha ramal nao completa ligacoes sem sinal aparelho telefonico",
     "passos": ["Confira se o cabo do aparelho está firme no aparelho e na tomada.", "Teste outro aparelho na mesma tomada para saber se o defeito é no aparelho ou na linha.",
                "Se a linha continuar sem tom, anote o ramal e o local e abra a OS (pode depender da operadora)."]},
    {"id": "kb-rede", "titulo": "Computador sem rede / sem internet",
     "sintomas": "sem internet sem rede cabo de rede desconectado ponto de rede nao funciona wifi nao conecta computador sem acesso",
     "passos": ["Verifique se o cabo de rede está encaixado nas duas pontas e se a luz da placa de rede acende.", "Teste o cabo em outro ponto/computador.",
                "Reinicie o computador. Se vários computadores do setor estão sem rede, o problema é no switch/link: abra a OS informando quantos estão afetados."]},
    {"id": "kb-pc-inicia", "titulo": "Computador não inicia / reparo automático",
     "sintomas": "computador nao inicia reparo automatico tela azul nao liga reinicia sozinho superaquece lento travando",
     "passos": ["Desligue da tomada por 30 segundos e ligue novamente.", "Desconecte pendrives e periféricos e tente iniciar.",
                "Se aparecer reparo automático de novo, não insista: abra a OS informando o número do patrimônio (etiqueta)."]},
    {"id": "kb-senha", "titulo": "Senha bloqueada / expirada / sem acesso ao e-mail",
     "sintomas": "senha bloqueada senha expirada nao consigo logar sem acesso email nao envia nao recebe dominio usuario",
     "passos": ["Confira se a tecla Caps Lock está desligada e o idioma do teclado.", "Aguarde 15 minutos se errou a senha várias vezes (bloqueio automático).",
                "Se continuar, abra a OS com o nome de usuário (não informe a senha)."]},
    {"id": "kb-impressora", "titulo": "Impressora não imprime / atolamento",
     "sintomas": "impressora nao imprime offline atolamento de papel multifuncional toner fila de impressao",
     "passos": ["Verifique papel, toner e se há papel atolado (abra a tampa e retire com cuidado).", "Desligue e ligue a impressora e confira se aparece online no computador.",
                "Se persistir, abra a OS com modelo e patrimônio da impressora."]},
    {"id": "kb-video", "titulo": "Monitor sem imagem / cabo HDMI",
     "sintomas": "monitor sem imagem piscando cabo hdmi painel tv projetor sem video",
     "passos": ["Confira o cabo (HDMI/VGA) nas duas pontas e a fonte de entrada do monitor/TV.", "Teste outro cabo ou outra entrada.",
                "Para instalar painel/TV, informe o comprimento do cabo necessário e o local: abra a OS."]},
    {"id": "kb-predial", "titulo": "Reparo predial (lâmpada, torneira, vazamento)",
     "sintomas": "lampada queimada luminaria vazamento torneira quebrada banheiro infiltracao porta fechadura",
     "passos": ["Em caso de vazamento, feche o registro mais próximo para evitar danos.", "Fotografe o problema e informe o local exato (andar/sala).", "Abra a OS com a foto."]},
]


def _tf(ts: list[str]) -> Counter:
    return Counter(ts)


def _kb_extra(db: Session) -> list[dict]:
    c = db.get(Config, "kb_extra")
    return list(c.valor.get("itens", [])) if c else []


def adicionar_conhecimento(db: Session, titulo: str, sintomas: str, passos: list[str]) -> dict:
    c = db.get(Config, "kb_extra")
    itens = list(c.valor.get("itens", [])) if c else []
    item = {"id": f"kb-x{len(itens) + 1}", "titulo": titulo.strip(), "sintomas": sintomas.strip() or titulo, "passos": [p for p in passos if p.strip()]}
    itens.append(item)
    if c:
        c.valor = {"itens": itens}
    else:
        db.add(Config(chave="kb_extra", valor={"itens": itens}))
    db.flush()
    return item


def _docs(db: Session) -> list[dict]:
    docs = []
    for k in KB_BASE + _kb_extra(db):
        docs.append({"tipo": "kb", "id": k["id"], "titulo": k["titulo"], "texto": f"{k['titulo']} {k['sintomas']}", "passos": k["passos"]})
    q = select(Tarefa).where(Tarefa.status.in_(["RESOLVIDA", "CONCLUIDA_EXECUTOR"]))
    for t in db.scalars(q).all():
        concl = next((e for e in reversed(t.eventos) if e.tipo == "concluida"), None)
        if not concl or len(concl.texto.strip()) < 15:           # OS sem registro útil ("OS ok", "N/D") não ensina nada
            continue
        solucao = concl.texto.strip()
        for i in t.impedimentos:
            if i.resolucao:
                solucao += f" (impedimento: {i.descricao.strip()[:80]} → {i.resolucao.strip()[:80]})"
        docs.append({"tipo": "os", "id": t.id, "titulo": t.titulo, "texto": f"{t.titulo} {t.descricao}", "solucao": solucao,
                     "local": t.local, "unidade": t.unidade_demandante, "quando": t.criado_em, "nota": t.avaliacao})
    return docs


def _boost(db: Session) -> dict[str, float]:
    """Fontes que ajudaram (👍) sobem; fontes que não ajudaram (👎) descem — aprendizado com feedback humano."""
    b: dict[str, float] = {}
    for c in db.scalars(select(ChatConversa).where(ChatConversa.resolveu.is_not(None))).all():
        for f in c.fontes or []:
            k = f"{f.get('tipo')}:{f.get('id')}"
            b[k] = b.get(k, 0.0) + (0.08 if c.resolveu else -0.08)
    return b


def buscar(db: Session, consulta: str, k: int = 3) -> list[dict]:
    docs = _docs(db)
    consulta_t = ai.tokens(consulta)
    if not docs or not consulta_t:
        return []
    toks = [_tf(ai.tokens(d["texto"])) for d in docs]
    n = len(docs)
    df: Counter = Counter()
    for t in toks:
        df.update(t.keys())
    idf = {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in df.items()}

    def vet(c: Counter) -> dict:
        return {w: v * idf.get(w, math.log(n + 1) + 1.0) for w, v in c.items()}

    q = vet(_tf(consulta_t)); qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
    boost = _boost(db)
    saida = []
    for d, t in zip(docs, toks):
        v = vet(t); vn = math.sqrt(sum(x * x for x in v.values())) or 1.0
        sc = sum(q[w] * v.get(w, 0.0) for w in q) / (qn * vn)
        sc = max(0.0, sc + boost.get(f"{d['tipo']}:{d['id']}", 0.0) * (1 if sc > 0.05 else 0))
        if sc > 0.05:
            saida.append({**d, "score": round(sc, 3)})
    saida.sort(key=lambda x: -x["score"])
    return saida[:k]


def similares(db: Session, texto: str, k: int = 3) -> list[dict]:
    """Casos parecidos já resolvidos (painel do atendente durante a ligação)."""
    return [{"tarefa_id": r["id"], "titulo": r["titulo"], "solucao": r["solucao"], "score": r["score"],
             "local": r.get("local", "")} for r in buscar(db, texto, 6) if r["tipo"] == "os"][:k]


def recorrencia_local(db: Session, local_id: Optional[int], dias: int = 90) -> int:
    if not local_id:
        return 0
    desde = agora() - timedelta(days=dias)
    return len(db.scalars(select(Tarefa.id).where(Tarefa.local_id == local_id, Tarefa.criado_em >= desde)).all())


def _redigir(pergunta: str, achados: list[dict], base: str) -> tuple[str, str]:
    if not OLLAMA_URL:
        return base, "recuperação local (sem LLM)"
    ctx = "\n".join(f"- {a['titulo']}: " + (" ".join(a.get("passos", [])) or a.get("solucao", "")) for a in achados)
    prompt = ("Você é o assistente de suporte técnico da prefeitura. Responda em português, curto e prático, usando SOMENTE o contexto. "
              f"Se faltar informação, diga o que perguntar.\nContexto:\n{ctx}\n\nPergunta: {pergunta}")
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=30)
        r.raise_for_status()
        return r.json()["response"].strip(), f"LLM local ({OLLAMA_MODEL}) sobre casos recuperados"
    except Exception as e:
        return base, f"recuperação local (LLM indisponível: {type(e).__name__})"


def responder(db: Session, usuario_id: Optional[int], pergunta: str, local: str = "") -> dict:
    achados = buscar(db, pergunta, 4)
    melhor = achados[0]["score"] if achados else 0.0
    cls = ai.classificar(db, pergunta, "")
    categoria = cls["classificacao"][0] if cls["classificacao"] else None
    if melhor >= LIMIAR:
        kb = next((a for a in achados if a["tipo"] == "kb"), None)
        oss = [a for a in achados if a["tipo"] == "os"][:2]
        partes = []
        if kb:
            partes.append(f"**{kb['titulo']}** — tente primeiro:\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(kb["passos"], 1)))
        if oss:
            partes.append("**Como casos parecidos foram resolvidos:**\n" + "\n".join(
                f"• OS #{o['id']} ({o['quando']:%d/%m/%Y}{', ' + o['local'] if o.get('local') else ''}): {o['solucao']}" for o in oss))
        partes.append("Se isso não resolver, abra a OS — vou levar estas informações junto. 🔧")
        base = "\n\n".join(partes)
        texto, modo = _redigir(pergunta, achados, base)
        acao = {"abrir_os": categoria is not None, "categoria": categoria["rotulo"] if categoria else None}
        confianca = "alta" if melhor >= 0.5 else "media"
    else:
        faltas = ai.lacunas(type("T", (), dict(titulo=pergunta, descricao=pergunta, unidade_demandante="", local=local,
                                              solicitante_contato="", extra={}))(), categoria["categoria"] if categoria else None)
        perg = "\n".join(f"• {f['pergunta']}" for f in faltas[:3]) or "• Descreva o sintoma, o local e o equipamento (patrimônio)."
        texto = ("Ainda não tenho um caso parecido registrado para isso. Para eu ajudar (ou para abrir uma OS completa), me conte:\n" + perg)
        modo, acao, confianca = "sem caso parecido", {"abrir_os": True, "categoria": categoria["rotulo"] if categoria else None}, "baixa"
    c = ChatConversa(usuario_id=usuario_id, pergunta=pergunta[:1000], resposta=texto, melhor_score=melhor,
                     fontes=[{"tipo": a["tipo"], "id": a["id"], "score": a["score"]} for a in achados[:3]])
    db.add(c)
    db.flush()
    return {"conversa_id": c.id, "resposta": texto, "confianca": confianca, "modo": modo, "acao": acao,
            "fontes": [{"tipo": a["tipo"], "id": a["id"], "titulo": a["titulo"], "score": a["score"]} for a in achados[:3]]}


def resumo(db: Session, dias: int = 90) -> dict:
    desde = agora() - timedelta(days=dias)
    cs = db.scalars(select(ChatConversa).where(ChatConversa.criado_em >= desde)).all()
    com_fb = [c for c in cs if c.resolveu is not None]
    resolvidas = [c for c in com_fb if c.resolveu]
    sem_resposta = Counter(c.pergunta.strip().lower()[:80] for c in cs if c.melhor_score < LIMIAR)
    return {"janela_dias": dias, "perguntas": len(cs), "com_feedback": len(com_fb), "resolveram_sem_os": len(resolvidas),
            "taxa_deflexao": round(100 * len(resolvidas) / len(com_fb), 1) if com_fb else None,
            "abriram_os": sum(1 for c in cs if c.abriu_os),
            "lacunas_de_conhecimento": [{"pergunta": p, "vezes": n} for p, n in sem_resposta.most_common(8)],
            "mede": "Perguntas respondidas que o usuário marcou como 'resolveu' (sem precisar abrir OS) ÷ perguntas com feedback.",
            "fonte": "Tabela chat_conversas (feedback 👍/👎)."}
