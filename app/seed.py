"""Dados de demonstração — 100% FICTÍCIOS (nomes, unidades e relatos), inspirados nos temas das OS de amostra.
Mostram a plataforma GENÉRICA: TI (help desk), manutenção predial, fiscalização e serviços urbanos.
"""
from __future__ import annotations
import os
import random
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import (Equipe, Notificacao, Setor, SistemaOrigem, TipoTarefa, Usuario, agora)
from .security import hash_senha
from .services import gamification, workflow

SENHA_DEMO = "demo123"
LEGADO_KEY = os.getenv("LEGADO_API_KEY", "demo-legado-key")
LEGADO_WEBHOOK = os.getenv("LEGADO_WEBHOOK_URL", "http://localhost:9000/webhook/plataforma")
LEGADO_WEBHOOK_KEY = os.getenv("LEGADO_WEBHOOK_KEY", "demo-webhook-key")


def semear(db: Session) -> None:
    if db.scalar(select(Setor).limit(1)):
        return
    # ---------------------------------------------------------------- estrutura
    setores = {n: Setor(nome=n, sigla=s) for n, s in [
        ("Help Desk de TI", "TI"), ("Manutenção Predial", "PRED"), ("Vistorias e Fiscalização", "FISC"),
        ("Serviços Urbanos", "URB")]}
    db.add_all(setores.values())
    db.flush()
    ti, pred, fisc, urb = (setores[n] for n in ["Help Desk de TI", "Manutenção Predial", "Vistorias e Fiscalização", "Serviços Urbanos"])
    equipes = {}
    for nome, setor in [("HELP DESK", ti), ("SUPORTE TÉCNICO", ti), ("TELECOM", ti), ("TELEFONIA", ti), ("DATACENTER", ti),
                        ("FÁBRICA DE SOFTWARE", ti), ("AQUISIÇÕES/ESTOQUE", ti), ("MANUTENÇÃO PREDIAL", pred),
                        ("FISCALIZAÇÃO", fisc), ("ZELADORIA", urb)]:
        equipes[nome] = Equipe(nome=nome, setor_id=setor.id)
        db.add(equipes[nome])
    db.flush()
    E = lambda n: equipes[n].id  # noqa: E731
    tipos = [
        # nome, setor, equipe, complexidade, sla_min, evidência, validação, campos obrigatórios
        ("Ponto de rede / conectividade", ti, "TELECOM", "media", 240, True, True, ["local", "ramal"]),
        ("Telefonia / ramal", ti, "TELEFONIA", "media", 480, False, True, ["local"]),
        ("Computador / hardware", ti, "SUPORTE TÉCNICO", "media", 240, False, True, ["local"]),
        ("Impressora / periférico", ti, "SUPORTE TÉCNICO", "baixa", 480, False, True, []),
        ("Acesso / senha / e-mail", ti, "HELP DESK", "baixa", 60, False, True, []),
        ("Sistema / software", ti, "HELP DESK", "baixa", 120, False, True, []),
        ("Servidor / infraestrutura", ti, "DATACENTER", "alta", 60, True, True, []),
        ("Desenvolvimento / ajuste de sistema", ti, "FÁBRICA DE SOFTWARE", "alta", 1440, False, True, []),
        ("Material / equipamento", ti, "AQUISIÇÕES/ESTOQUE", "baixa", 480, False, True, []),
        ("Reparo predial", pred, "MANUTENÇÃO PREDIAL", "media", 480, True, True, ["local"]),
        ("Vistoria", fisc, "FISCALIZAÇÃO", "media", 1440, True, True, ["local"]),
        ("Serviço urbano", urb, "ZELADORIA", "media", 1440, True, True, ["local"]),
    ]
    tp = {}
    for nome, setor, eq, comp, sla, evid, val, campos in tipos:
        tp[nome] = TipoTarefa(nome=nome, setor_id=setor.id, equipe_padrao_id=E(eq), complexidade=comp, sla_inicio_min=sla,
                              exige_evidencia=evid, exige_validacao=val, campos_obrigatorios=campos)
        db.add(tp[nome])
    # ---------------------------------------------------------------- usuários (fictícios)
    h = hash_senha(SENHA_DEMO)

    def U(nome, login, perfis, eq=None, setor=None, av="🧭", contato=""):
        u = Usuario(nome=nome, login=login, senha_hash=h, perfis=perfis, equipe_id=E(eq) if eq else None,
                    setor_id=setor.id if setor else None, avatar=av, contato=contato)
        db.add(u)
        return u
    U("Administrador SIMOT", "admin", "admin", av="🛡️")
    U("Camila Atendente", "atendente1", "atendente", setor=ti, av="🎧", contato="ramal 6800")
    U("Rogério Atendente", "atendente2", "atendente", setor=ti, av="🎧", contato="ramal 6801")
    U("Helena Gestora (TI)", "gestor", "gestor,atendente", setor=ti, av="🧠")
    U("Marcos Gestor (Predial)", "gestor2", "gestor", setor=pred, av="🧱")
    execs = [
        ("Bruno Tavares", "exec1", "HELP DESK", ti, "🦊"), ("Larissa Moura", "exec2", "SUPORTE TÉCNICO", ti, "🐺"),
        ("Diego Fontes", "exec3", "TELECOM", ti, "🦉"), ("Paula Reis", "exec4", "TELEFONIA", ti, "🐱"),
        ("Tiago Lemos", "exec5", "DATACENTER", ti, "🐉"), ("Nina Prado", "exec6", "SUPORTE TÉCNICO", ti, "🦄"),
        ("Otávio Braga", "exec7", "MANUTENÇÃO PREDIAL", pred, "🛠️"), ("Sônia Maia", "exec8", "FISCALIZAÇÃO", fisc, "🔍"),
        ("Caio Ventura", "exec9", "ZELADORIA", urb, "🌳")]
    for nome, login, eq, setor, av in execs:
        U(nome, login, "executor", eq, setor, av)
    dems = [("Patrícia Souza", "dem1", "UPA Afonso Pena (fictícia)"), ("Mariana Lima", "dem2", "Escola Municipal Rural (fictícia)"),
            ("Antônio Pereira", "dem3", "Cemitério Municipal (fictício)"), ("Lúcia Ferraz", "dem4", "Dept. de Recursos Humanos"),
            ("Renato Gomes", "dem5", "Unidade de Saúde Borda do Campo (fictícia)")]
    for nome, login, un in dems:
        U(nome, login, "demandante", setor=None, av="🙋", contato=un)
    db.add(SistemaOrigem(codigo="HELPDESK-LEGADO", nome="Help Desk Municipal (legado simulado)", api_key=LEGADO_KEY,
                         webhook_url=LEGADO_WEBHOOK, webhook_key=LEGADO_WEBHOOK_KEY, setor_padrao_id=ti.id))
    db.commit()

    # ---------------------------------------------------------------- histórico simulado
    _historico(db, tp)
    db.execute(update(Notificacao).values(lida=True))   # histórico não gera "alertas" na demo
    db.commit()


def _historico(db: Session, tp: dict) -> None:
    rnd = random.Random(2026)
    U = lambda login: db.scalar(select(Usuario).where(Usuario.login == login))  # noqa: E731
    gestor, gestor2, atend = U("gestor"), U("gestor2"), U("atendente1")
    hoje = agora()
    inicio_mes = hoje.replace(day=1, hour=8, minute=0, second=0, microsecond=0)
    mes_ant = (inicio_mes - timedelta(days=1)).replace(day=3, hour=8)

    def jornada(titulo, desc, tipo, dem, exs, base, fim, nota=None, imp=None, unidade="", local="", ramal="", apoio=None,
                prioridade=None):
        t_ = tp[tipo]
        setor_id = t_.setor_id
        g = gestor2 if setor_id == tp["Reparo predial"].setor_id else gestor
        d = U(dem)
        t = workflow.criar_tarefa(db, titulo=titulo, descricao=desc, setor_id=setor_id, tipo_id=t_.id,
                                  local=local or "Local informado na ligação", unidade_demandante=unidade or d.contato,
                                  solicitante_nome=d.nome, solicitante_contato=ramal or "ramal 3380", demandante_id=d.id,
                                  atendente=atend, prioridade=prioridade, quando=base)
        if fim == "nova":
            db.commit(); return t
        ids = [U(x).id for x in exs] + ([U(apoio).id] if apoio else [])
        q = base + timedelta(minutes=rnd.randint(15, 90))
        workflow.atribuir(db, t, g, ids, quando=q)
        if fim == "atribuida":
            db.commit(); return t
        ex = U(exs[0])
        q += timedelta(minutes=rnd.choice([12, 25, 40, 70, 150, 300]))
        workflow.iniciar(db, t, ex, quando=q)
        q += timedelta(minutes=20)
        workflow.andamento(db, t, ex, "Diagnóstico realizado no local.", quando=q)
        if imp:
            q += timedelta(minutes=15)
            workflow.registrar_impedimento(db, t, ex, imp[0], imp[1], quando=q)
            if fim == "bloqueada":
                db.commit(); return t
            q += timedelta(minutes=rnd.randint(60, 240))
            workflow.resolver_impedimento(db, t, g, imp[2], quando=q)
        if fim == "andamento":
            db.commit(); return t
        q += timedelta(minutes=rnd.randint(30, 120))
        workflow.concluir(db, t, ex, "Serviço executado e testado com o usuário.", [{"arquivo": "demo/evidencia.png", "nome": "foto.png", "mime": "image/png"}] if t_.exige_evidencia else None, quando=q)
        if fim == "concluida":
            db.commit(); return t
        q += timedelta(minutes=rnd.randint(30, 600))
        if fim == "pendente":
            workflow.validar(db, t, resolvido=False, motivo_pendencia="O problema voltou a ocorrer na mesma sala.", ator="demandante", quando=q)
        else:
            workflow.validar(db, t, resolvido=True, nota=nota, comentario="Atendimento ok.", ator="demandante", quando=q)
        db.commit()
        return t

    # --------------- mês anterior (placar fechado automaticamente na virada; histórico preservado)
    ant = [
        ("Telefone mudo no setor", "Telefone mudo, sem tom de linha desde ontem.", "Telefonia / ramal", "dem3", ["exec4"], 5, None),
        ("Computador não inicia", "Máquina apresenta reparo automático ao iniciar, consultório 7.", "Computador / hardware", "dem1", ["exec2"], 4, None),
        ("Sala sem ponto de rede", "Sala de informática sem ponto de rede, precisa de 5 máquinas.", "Ponto de rede / conectividade", "dem2", ["exec3"], 5, ("material", "Faltam 40 metros de cabo de rede categoria 6 para o ponto", "Cabo retirado no estoque e entregue")),
        ("Senha bloqueada", "Usuário bloqueado no domínio, não consigo logar.", "Acesso / senha / e-mail", "dem4", ["exec1"], 5, None),
        ("Impressora não imprime", "Impressora multifuncional offline, não responde.", "Impressora / periférico", "dem5", ["exec6"], 4, None),
        ("Servidor de arquivos lento", "Servidor de arquivos muito lento para todos os usuários.", "Servidor / infraestrutura", "dem4", ["exec5"], 4, None),
        ("Lâmpadas queimadas no corredor", "Trocar luminárias do corredor do segundo andar.", "Reparo predial", "dem4", ["exec7"], 5, None),
        ("Buraco na rua em frente à escola", "Buraco grande, risco para ônibus escolar.", "Serviço urbano", "dem2", ["exec9"], 4, None),
        ("Internet lenta na unidade", "Wifi não conecta e a internet está lenta.", "Ponto de rede / conectividade", "dem5", ["exec3"], 3, ("terceiro", "Link da operadora instável, aberto protocolo com a operadora", "Operadora normalizou o link")),
        ("Acesso ao sistema de protocolo", "Criar acesso ao sistema para novo servidor.", "Acesso / senha / e-mail", "dem4", ["exec1"], 5, None),
        ("Monitor sem imagem", "Monitor piscando e sem imagem.", "Computador / hardware", "dem1", ["exec6"], 5, None),
        ("Vistoria de obra irregular", "Denúncia de obra sem alvará.", "Vistoria", "dem2", ["exec8"], 4, None),
    ]
    for i, (ti_, de, tipo, dem, ex, nota, imp) in enumerate(ant):
        jornada(ti_, de, tipo, dem, ex, mes_ant + timedelta(days=i * 2, minutes=rnd.randint(0, 200)), "resolvida", nota, imp,
                apoio="exec6" if i % 4 == 0 and ex[0] != "exec6" and tipo.endswith("hardware") else None)

    # --------------- mês atual
    b = lambda d, m=0: inicio_mes + timedelta(days=d, minutes=m)  # noqa: E731
    corr = [
        ("Telefone mudo no cemitério", "Telefone mudo, sem linha. Endereço na rodovia.", "Telefonia / ramal", "dem3", ["exec4"], 5, ("terceiro", "Linha depende da operadora, aberto protocolo com a operadora", "Operadora restabeleceu a linha")),
        ("Cabo HDMI para painel", "Usuária solicita um cabo HDMI de 15 metros para instalação do painel.", "Material / equipamento", "dem5", ["exec1"], 5, None),
        ("Reinício automático do computador", "Computador reinicia sozinho e superaquece.", "Computador / hardware", "dem1", ["exec2"], 4, None),
        ("Ponto de rede na recepção", "Ponto de rede não funciona na recepção.", "Ponto de rede / conectividade", "dem1", ["exec3"], 5, ("material", "Falta patch cord e conector para o ponto", "Material entregue pelo estoque")),
        ("E-mail não envia", "Email não envia nem recebe mensagens.", "Acesso / senha / e-mail", "dem4", ["exec1"], 5, None),
        ("Nobreak do datacenter com alarme", "Nobreak com alarme sonoro, verificar baterias.", "Servidor / infraestrutura", "dem4", ["exec5"], 4, None),
    ]
    dia = 1
    for ti_, de, tipo, dem, ex, nota, imp in corr:
        jornada(ti_, de, tipo, dem, ex, b(dia, rnd.randint(0, 120)), "resolvida", nota, imp)
        dia += 1
    jornada("Impressora com atolamento", "Impressora com atolamento de papel recorrente.", "Impressora / periférico", "dem2", ["exec6"], b(dia), "concluida")
    jornada("Instalar ponto de rede nova sala", "Instalar ponto de rede novo na sala de reuniões. Urgente: pacientes aguardando.", "Ponto de rede / conectividade", "dem5", ["exec3"], b(dia, 30), "concluida",
            unidade="Unidade de Saúde (fictícia)", ramal="ramal 5521")
    jornada("Computador do consultório lento", "Computador muito lento, travando durante atendimento.", "Computador / hardware", "dem5", ["exec2"], b(dia + 1), "pendente")
    jornada("Troca de patch cord na escola", "Cabo de rede rompido na escola.", "Ponto de rede / conectividade", "dem2", ["exec3"], b(dia + 1, 60), "bloqueada",
            imp=("material", "Faltam cabos de rede e conectores no almoxarifado, aguardando reposição", ""))
    jornada("Servidor de backup sem espaço", "Backup não executou ontem, máquina virtual sem espaço em disco.", "Servidor / infraestrutura", "dem4", ["exec5"], b(dia + 1, 90), "andamento")
    jornada("Vazamento no banheiro", "Vazamento de água no banheiro, torneira quebrada.", "Reparo predial", "dem4", ["exec7"], b(dia + 2), "atribuida")
    jornada("Telefone sem tom na escola", "Ramal não completa ligações.", "Telefonia / ramal", "dem2", ["exec4"], b(dia + 2, 20), "atribuida")
    jornada("Senha expirada", "Senha expirada, não consigo entrar na rede.", "Acesso / senha / e-mail", "dem4", [], b(dia + 3), "nova")
    jornada("Poda de árvore sobre a fiação", "Poda de árvore caindo sobre a fiação elétrica, risco.", "Serviço urbano", "dem3", [], b(dia + 3, 40), "nova")
    db.commit()
    gamification.periodo_ativo(db)
    db.commit()
