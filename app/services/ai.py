"""IA local (Requisito 6) — roda 100% dentro do datacenter, sem enviar dados para fora.

Problema escolhido: o atendente recebe a ligação e precisa decidir RÁPIDO para qual equipe encaminhar, com que
prioridade, e se faltou alguma informação que obrigará o técnico a voltar ou ligar de novo.
Nas OS reais de amostra, quase todas as atualizações de execução ficaram como "N/D" e uma OS ficou aberta
17 meses com 2 reaberturas: informação faltante e encaminhamento errado custam tempo.

Quatro funções, todas com CONFERÊNCIA HUMANA (nada muda sozinho):
 1. classificar()          – Naive Bayes multinomial treinado localmente; devolve top-3 com as palavras que pesaram.
 2. lacunas()              – detecta informações faltantes e sugere perguntas ao atendente.
 3. resumir()              – resumo dos relatos da execução (regras; usa LLM local via Ollama se OLLAMA_URL).
 4. impedimentos_recorrentes() – agrega impedimentos para a gestão agir na causa.

O que é REAL no protótipo: o classificador (treina em ~ms no start, sem biblioteca externa), as regras de
prioridade e de lacunas, a agregação de impedimentos. O que é SIMULADO: o corpus de treino é sintético (escrito a
partir dos temas das OS de amostra e das categorias do help desk); em produção treina-se com a descrição real dos chamados
do legado. O LLM local (Ollama) é opcional e só melhora o texto do resumo.
"""
from __future__ import annotations
import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import OLLAMA_MODEL, OLLAMA_URL
from ..models import Equipe, Impedimento, Tarefa, TipoTarefa

STOP = set("""a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre e ou que se ao aos à às
 foi ser esta este essa esse isso isto ja nao não mais muito pouco tem ter tinha como quando onde quem the usuario usuária
 usuaria solicita solicitou relata informa precisa favor por-favor bom dia boa tarde noite gentileza urgente""".split())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokens(texto: str) -> list[str]:
    ws = [w for w in re.findall(r"[a-z0-9]+", _norm(texto)) if len(w) >= 3 and w not in STOP]
    return ws + [f"{a}_{b}" for a, b in zip(ws, ws[1:])]


# ---------------------------------------------------------------------- corpus sintético (por categoria)
CORPUS: dict[str, list[str]] = {
    "rede": [
        "sala sem ponto de rede e sem tomadas precisa de cinco maquinas em uso",
        "computador sem acesso a internet cabo de rede desconectado",
        "ponto de rede nao funciona na recepcao",
        "internet lenta na unidade todos os computadores sem navegar",
        "wifi nao conecta no setor precisa de access point",
        "instalar ponto de rede novo na sala de informatica",
        "switch com portas queimadas sem link na unidade",
        "rede caiu no predio inteiro sem comunicacao com servidor",
        "cabo de rede rompido na escola precisa de passagem de cabeamento",
        "link de internet da unidade de saude fora do ar",
        "sem rede no consultorio nao consigo acessar o sistema",
        "pontos de rede insuficientes para novos computadores",
    ],
    "telefonia": [
        "telefone mudo no cemiterio sem linha",
        "ramal nao completa ligacoes telefone sem tom",
        "telefone nao toca quando recebe chamada ramal com problema",
        "instalar ramal novo no setor",
        "aparelho telefonico com defeito sem audio",
        "central telefonica sem linha externa",
        "telefone fixo da unidade esta mudo ha dias",
        "ligacao cai constantemente ramal com ruido",
        "transferir ramal para outro setor mudanca de sala",
        "linha telefonica cortada sem sinal na escola",
        "fone de ouvido do telefone ip sem som",
    ],
    "computador": [
        "maquina do usuario apresenta problema ao iniciar reparo automatico",
        "computador nao liga tela preta",
        "computador muito lento travando precisa de formatacao",
        "monitor sem imagem piscando",
        "notebook nao carrega bateria",
        "all in one nao inicia windows erro disco",
        "computador reinicia sozinho superaquecendo",
        "troca de memoria e hd computador sem desempenho",
        "teclado e mouse nao funcionam na maquina",
        "computador com barulho no cooler desliga sozinho",
        "windows nao atualiza e computador sem espaco em disco",
        "tela azul no computador do consultorio",
    ],
    "impressora": [
        "impressora nao imprime atolamento de papel",
        "impressora fora de rede nao encontra no computador",
        "toner acabou impressora com manchas",
        "instalar impressora nova no setor driver",
        "scanner nao digitaliza documentos",
        "impressora multifuncional com erro na tela",
        "impressao saindo em branco ou com listras",
        "impressora offline nao responde",
    ],
    "acesso": [
        "esqueci a senha do computador preciso redefinir",
        "usuario bloqueado no dominio nao consigo logar",
        "criar acesso ao sistema para novo servidor",
        "email nao envia nem recebe mensagens",
        "liberar permissao de pasta compartilhada",
        "senha expirada nao consigo entrar na rede",
        "criar usuario de email para novo funcionario",
        "acesso negado ao sistema de protocolo",
        "preciso de acesso vpn para trabalho remoto",
        "conta de email cheia sem espaco",
    ],
    "software": [
        "sistema apresenta erro ao abrir relatorio",
        "instalar programa no computador licenca office",
        "navegador com erro ao acessar o portal",
        "atualizar sistema de ponto eletronico travando",
        "antivirus detectou ameaca no computador",
        "programa pdf nao abre arquivos",
        "instalacao do sistema de prontuario eletronico",
        "sistema lento e apresenta mensagem de erro ao salvar",
    ],
    "infra": [
        "servidor de arquivos fora do ar datacenter",
        "backup nao executou ontem servidor",
        "maquina virtual sem espaco em disco datacenter",
        "sistema indisponivel para todos os usuarios servidor caiu",
        "certificado do site expirou servidor web",
        "banco de dados lento consultas travando",
        "vpn entre unidades sem conexao firewall",
        "nobreak do datacenter com alarme",
    ],
    "desenvolvimento": [
        "solicito novo relatorio no sistema desenvolvimento",
        "ajuste no formulario do portal desenvolver nova funcionalidade",
        "integracao entre sistemas precisa de desenvolvimento",
        "alterar fluxo do sistema de protocolo nova regra",
        "criar painel de indicadores para a secretaria",
        "automatizar planilha com rotina em sistema",
    ],
    "material": [
        "usuaria solicita um cabo hdmi de quinze metros para instalacao do painel",
        "preciso de mouse e teclado novos",
        "solicito toner e suprimentos de informatica",
        "retirar equipamento no estoque para novo posto de trabalho",
        "compra de cabos adaptadores e fonte para notebook",
        "solicito monitor adicional entrega de equipamento",
        "falta material para instalacao patch cord conectores",
        "requisicao de pecas para reparo de equipamento",
    ],
    "predial": [
        "infiltracao no teto da sala goteira quando chove",
        "lampada queimada no corredor trocar luminaria",
        "vazamento de agua no banheiro torneira quebrada",
        "tomada soltando faiscas problema eletrico",
        "porta emperrada fechadura quebrada",
        "ar condicionado nao gela manutencao",
        "pintura descascando na parede reforma",
        "telhado com telhas quebradas",
    ],
    "vistoria": [
        "vistoria no imovel denuncia de obra irregular",
        "fiscalizar construcao sem alvara",
        "vistoria tecnica para liberacao de habite-se",
        "inspecao de risco em encosta moradores preocupados",
        "vistoria sanitaria em estabelecimento comercial",
        "verificar denuncia de descarte irregular de entulho",
    ],
    "zeladoria": [
        "buraco na rua tapa buraco urgente",
        "poda de arvore caindo sobre a fiacao",
        "mato alto no terreno publico roçada",
        "lixo acumulado na calcada coleta nao passou",
        "boca de lobo entupida alagamento na rua",
        "iluminacao publica apagada poste sem luz",
        "sinalizacao de transito danificada placa caida",
    ],
}

# categoria -> (nome da equipe sugerida, nome do tipo de tarefa) — resolvido por nome no banco
DESTINO = {
    "rede": ("TELECOM", "Ponto de rede / conectividade"),
    "telefonia": ("TELEFONIA", "Telefonia / ramal"),
    "computador": ("SUPORTE TÉCNICO", "Computador / hardware"),
    "impressora": ("SUPORTE TÉCNICO", "Impressora / periférico"),
    "acesso": ("HELP DESK", "Acesso / senha / e-mail"),
    "software": ("HELP DESK", "Sistema / software"),
    "infra": ("DATACENTER", "Servidor / infraestrutura"),
    "desenvolvimento": ("FÁBRICA DE SOFTWARE", "Desenvolvimento / ajuste de sistema"),
    "material": ("AQUISIÇÕES/ESTOQUE", "Material / equipamento"),
    "predial": ("MANUTENÇÃO PREDIAL", "Reparo predial"),
    "vistoria": ("FISCALIZAÇÃO", "Vistoria"),
    "zeladoria": ("ZELADORIA", "Serviço urbano"),
}
ROTULO = {k: v[1] for k, v in DESTINO.items()}


class _NaiveBayes:
    def __init__(self, corpus: dict[str, list[str]]):
        self.classes = list(corpus)
        self.cont: dict[str, Counter] = {c: Counter() for c in self.classes}
        self.total: dict[str, int] = {}
        vocab = set()
        for c, frases in corpus.items():
            for f in frases:
                tk = tokens(f)
                self.cont[c].update(tk)
                vocab.update(tk)
        self.V = len(vocab)
        self.total = {c: sum(self.cont[c].values()) for c in self.classes}
        self.prior = {c: math.log(1 / len(self.classes)) for c in self.classes}  # classes equilibradas

    def log_prob(self, c: str, tk: list[str]) -> float:
        s = self.prior[c]
        for w in tk:
            s += math.log((self.cont[c][w] + 0.5) / (self.total[c] + 0.5 * self.V))
        return s

    def prever(self, texto: str, k: int = 3) -> list[dict]:
        tk = tokens(texto)
        if not tk:
            return []
        logs = {c: self.log_prob(c, tk) for c in self.classes}
        m = max(logs.values())
        exps = {c: math.exp(v - m) for c, v in logs.items()}
        z = sum(exps.values())
        ordem = sorted(self.classes, key=lambda c: -logs[c])
        saida = []
        for i, c in enumerate(ordem[:k]):
            rival = ordem[1] if i == 0 else ordem[0]
            peso = []
            for w in set(tk):
                if self.cont[c][w] == 0:
                    continue
                pc = math.log((self.cont[c][w] + 0.5) / (self.total[c] + 0.5 * self.V))
                pr = math.log((self.cont[rival][w] + 0.5) / (self.total[rival] + 0.5 * self.V))
                peso.append((pc - pr, w))
            peso.sort(reverse=True)
            saida.append({"categoria": c, "confianca": round(exps[c] / z, 3),
                          "palavras": [w.replace("_", " ") for _, w in peso[:4] if _ > 0]})
        return saida


_modelo = _NaiveBayes(CORPUS)


# ---------------------------------------------------------------------- 1. classificação + prioridade
URGENTE = ["urgente", "parado", "parou", "emergencia", "paciente", "samu", "sem atendimento", "pronto atendimento",
           "risco", "alagamento", "faiscas", "caiu no predio", "todos os usuarios", "fora do ar", "indisponivel"]
ALTA_UNIDADES = ["upa", "unidade de saude", "hospital", "samu", "pronto", "guarda", "defesa civil", "ambulatorio", "caps"]


def prioridade_sugerida(texto: str, unidade: str = "") -> dict:
    t, u = _norm(texto), _norm(unidade)
    motivos = [p for p in URGENTE if p in t]
    saude = [p for p in ALTA_UNIDADES if p in u or p in t]
    if motivos and saude:
        return {"valor": "urgente", "motivos": [f"termo crítico: '{m}'" for m in motivos[:2]] + [f"unidade crítica: '{saude[0]}'"]}
    if motivos:
        return {"valor": "alta", "motivos": [f"termo crítico: '{m}'" for m in motivos[:3]]}
    if saude:
        return {"valor": "alta", "motivos": [f"unidade de atendimento direto: '{saude[0]}'"]}
    if any(p in t for p in ["solicito", "instalar", "novo", "criar", "compra"]):
        return {"valor": "baixa", "motivos": ["pedido planejável (instalação/solicitação)"]}
    return {"valor": "normal", "motivos": ["sem indício de urgência"]}


def _resolver_destino(db: Session, categoria: str) -> dict:
    eq_nome, tipo_nome = DESTINO[categoria]
    equipe = db.scalar(select(Equipe).where(Equipe.nome.ilike(eq_nome)))
    tipo = db.scalar(select(TipoTarefa).where(TipoTarefa.nome == tipo_nome))
    return {"equipe_id": equipe.id if equipe else None, "equipe": equipe.nome if equipe else eq_nome,
            "tipo_id": tipo.id if tipo else None, "tipo": tipo.nome if tipo else tipo_nome,
            "setor_id": equipe.setor_id if equipe else None}


def classificar(db: Session, texto: str, unidade: str = "") -> dict:
    previsoes = _modelo.prever(texto)
    classif = []
    for p in previsoes:
        d = _resolver_destino(db, p["categoria"])
        classif.append({**p, "rotulo": ROTULO[p["categoria"]], **d})
    return {"classificacao": classif, "prioridade": prioridade_sugerida(texto, unidade)}


# ---------------------------------------------------------------------- 2. lacunas
HARDWARE = {"computador", "impressora", "rede", "telefonia", "material"}
RE_LOCAL = re.compile(r"\b(sala|bloco|andar|consultorio|recepcao|rua|av\.?|avenida|setor|piso|predio|guiche|laboratorio|"
                      r"escola|unidade|upa|ubs|secretaria|departamento)\b")
RE_FONE = re.compile(r"(\(?\d{2}\)?\s?)?\d{4,5}[-\s]?\d{4}|\bramal\s*\d+|\b\d{4}\b")


def lacunas(t: Tarefa, categoria: Optional[str] = None) -> list[dict]:
    local, contato = (t.local or ""), (t.solicitante_contato or "")
    texto = _norm(f"{t.titulo or ''} {t.descricao or ''} {local}")
    saida = []
    if len(texto.strip()) < 25:
        saida.append({"campo": "descricao", "pergunta": "O relato está muito curto: qual é o sintoma exato e desde quando ocorre?"})
    if not local.strip() and not RE_LOCAL.search(texto):
        saida.append({"campo": "local", "pergunta": "Em que local exatamente (unidade, sala/andar) o técnico deve ir?"})
    if not contato.strip() and not RE_FONE.search(texto):
        saida.append({"campo": "contato", "pergunta": "Qual ramal/telefone do solicitante para o técnico confirmar a chegada?"})
    if categoria in HARDWARE and not re.search(r"\b(etiqueta|patrimonio|tombamento|serie)\b|\b\d{4,6}\b", texto) and categoria in ("computador", "impressora"):
        saida.append({"campo": "equipamento", "pergunta": "Qual a etiqueta/patrimônio do equipamento?"})
    if categoria == "material" and not re.search(r"\d", texto):
        saida.append({"campo": "quantidade", "pergunta": "Qual a quantidade/medida do material necessário?"})
    return saida


def analisar_demanda(db: Session, t: Tarefa) -> dict:
    texto = f"{t.titulo}. {t.descricao}"
    r = classificar(db, texto, t.unidade_demandante)
    top = r["classificacao"][0]["categoria"] if r["classificacao"] else None
    return {**r, "lacunas": lacunas(t, top), "estado": "pendente", "modelo": "naive-bayes-local",
            "aviso": "Sugestão automática: só altera a tarefa se um responsável aceitar."}


# ---------------------------------------------------------------------- 3. resumo da execução
def _resumo_regras(t: Tarefa) -> str:
    linhas = []
    por_tipo = defaultdict(list)
    for e in t.eventos:
        por_tipo[e.tipo].append(e)
    c = por_tipo.get("criada", [None])[0]
    if c:
        linhas.append(f"Demanda aberta em {c.criado_em:%d/%m %H:%M}: {t.titulo}.")
    a = por_tipo.get("atribuida", [])
    if a:
        linhas.append(f"Atribuída ({len(a)}×); último responsável: {a[-1].texto.replace('Atribuída a ', '').split('. Obs')[0]}.")
    i = por_tipo.get("iniciada", [])
    if i:
        espera = (i[0].criado_em - (t.atribuido_em or t.criado_em)).total_seconds() / 60
        linhas.append(f"Atendimento iniciado {int(espera)} min após a atribuição.")
    imps = por_tipo.get("impedimento", [])
    if imps:
        linhas.append(f"{len(imps)} impedimento(s): " + "; ".join(e.texto[:70] for e in imps) + ".")
    ands = por_tipo.get("andamento", [])
    if ands:
        linhas.append(f"{len(ands)} registro(s) de andamento. Último: “{ands[-1].texto[:90]}”.")
    cc = por_tipo.get("concluida", [])
    if cc:
        linhas.append(f"Conclusão informada: “{cc[-1].texto[:120]}”.")
    p = por_tipo.get("pendencia", [])
    if p:
        linhas.append(f"Demandante apontou pendência {len(p)}×: “{p[-1].texto[-90:]}”.")
    v = por_tipo.get("validada", [])
    if v:
        linhas.append(f"Resolução confirmada pelo demandante (nota {t.avaliacao}).")
    linhas.append(f"Situação atual: {t.status}.")
    return " ".join(linhas)


def resumir(t: Tarefa) -> dict:
    base = _resumo_regras(t)
    if OLLAMA_URL:
        try:
            prompt = ("Resuma em até 4 frases, em português do Brasil, o histórico desta tarefa municipal para o gestor, "
                      "sem inventar fatos:\n" + "\n".join(f"- {e.criado_em:%d/%m %H:%M} {e.ator}: {e.texto}" for e in t.eventos))
            r = httpx.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                           timeout=30)
            r.raise_for_status()
            return {"resumo": r.json()["response"].strip(), "modo": f"LLM local ({OLLAMA_MODEL})", "base_regras": base}
        except Exception as e:
            return {"resumo": base, "modo": f"regras (LLM local indisponível: {type(e).__name__})"}
    return {"resumo": base, "modo": "regras locais (sem LLM)"}


# ---------------------------------------------------------------------- 4. apoio e recorrência
def sugerir_apoio(db: Session, t: Tarefa, descricao: str) -> Optional[dict]:
    r = _modelo.prever(descricao, 1)
    if not r:
        return None
    d = _resolver_destino(db, r[0]["categoria"])
    if d["equipe_id"] and d["equipe_id"] != t.equipe_id and r[0]["confianca"] >= 0.5:
        return {"equipe_id": d["equipe_id"], "equipe": d["equipe"], "confianca": r[0]["confianca"],
                "motivo": f"o impedimento descrito é típico de '{ROTULO[r[0]['categoria']]}'"}
    return None


SUGESTAO_TIPO = {
    "material": "Rever estoque mínimo e kit-padrão do tipo de tarefa para este item.",
    "terceiro": "Acompanhar o prazo do terceiro/contrato e abrir cobrança formal.",
    "acesso": "Padronizar a liberação de acesso prévia (autorização antes do deslocamento).",
    "apoio": "Avaliar escala conjunta com a equipe de apoio mais acionada.",
    "divergencia": "Melhorar a triagem no atendimento (perguntas da IA de lacunas) para reduzir divergência.",
    "outro": "Classificar melhor os motivos para identificar a causa.",
}


def impedimentos_recorrentes(db: Session, setor_id: Optional[int] = None, limite: int = 8) -> list[dict]:
    q = select(Impedimento, Tarefa).join(Tarefa, Tarefa.id == Impedimento.tarefa_id)
    if setor_id:
        q = q.where(Tarefa.setor_id == setor_id)
    grupos: dict[str, list] = defaultdict(list)
    for imp, tar in db.execute(q).all():
        grupos[imp.tipo].append((imp, tar))
    saida = []
    for tipo, itens in grupos.items():
        cont = Counter()
        for imp, _ in itens:
            cont.update(set(w for w in tokens(imp.descricao) if "_" not in w and len(w) >= 4))
        termos = [{"termo": w, "ocorrencias": n} for w, n in cont.most_common(5) if n >= 2]
        saida.append({"tipo": tipo, "ocorrencias": len(itens), "termos_frequentes": termos,
                      "tarefas": sorted({tar.id for _, tar in itens})[:10],
                      "abertos": sum(1 for imp, _ in itens if not imp.resolvido_em),
                      "sugestao": SUGESTAO_TIPO.get(tipo, "")})
    saida.sort(key=lambda x: -x["ocorrencias"])
    return saida[:limite]
