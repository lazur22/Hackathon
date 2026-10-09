"""Teste ponta a ponta da jornada do Manual (seções 6 e 17) + requisitos 1–6.
Executar:  pytest -q
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/t.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/up"
os.environ["OUTBOX_INTERVALO_S"] = "3600"       # worker não interfere; sincronizamos manualmente

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import outbox as outbox_mod


class LegadoFalso:
    """Simula o webhook do legado: pode ficar fora do ar e é idempotente pela chave."""
    def __init__(self):
        self.no_ar = True
        self.recebidas: dict[str, dict] = {}

    def __call__(self, *a, **k):          # substitui httpx.Client(...)
        return self

    def post(self, url, json=None, headers=None):
        class R: pass
        r = R()
        if not self.no_ar:
            r.status_code = 503
            return r
        assert headers["X-API-Key"] == "demo-webhook-key"
        self.recebidas.setdefault(json["chave_idempotencia"], json)   # duplicatas são ignoradas
        r.status_code = 200
        return r


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cli:
        yield cli


def login(c, usuario):
    r = c.post("/api/v1/auth/login", json={"login": usuario, "senha": "demo123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


KEY = {"X-API-Key": "demo-legado-key"}


def test_jornada_completa(c, monkeypatch):
    legado = LegadoFalso()
    legado.no_ar = False                       # legado fora do ar no início (ver abaixo)
    monkeypatch.setattr(outbox_mod.httpx, "Client", legado)

    ger, ex, dem = login(c, "gestor"), login(c, "exec3"), login(c, "dem1")
    exec3_id = c.get("/api/v1/auth/eu", headers=ex).json()["id"]
    dem1_id = c.get("/api/v1/auth/eu", headers=dem).json()["id"]

    # 1-3) legado envia a demanda; reenvio NÃO duplica
    corpo = {"id_origem": "9001", "titulo": "Ponto de rede não funciona",
             "descricao": "Servidora liga informando que o ponto de rede da sala 3 não funciona",
             "tipo": "Ponto de rede / conectividade", "unidade": "UPA Afonso Pena (fictícia)", "local": "Sala 3",
             "solicitante": {"nome": "Patrícia Souza", "contato": "ramal 5521", "login": "dem1"}, "atendente": "Camila"}
    r1 = c.post("/api/v1/integracao/tarefas", json=corpo, headers=KEY)
    assert r1.status_code == 201 and r1.json()["duplicada"] is False
    tid = r1.json()["id_plataforma"]
    r2 = c.post("/api/v1/integracao/tarefas", json=corpo, headers=KEY)
    assert r2.json()["id_plataforma"] == tid and r2.json()["duplicada"] is True        # sem duplicidade
    assert c.post("/api/v1/integracao/tarefas", json=corpo, headers={"X-API-Key": "errada"}).status_code == 401

    # solicitante NÃO abre chamado; executor também não
    assert c.post("/api/v1/tarefas", json={"titulo": "xxx", "setor_id": 1}, headers=dem).status_code == 403
    assert c.post("/api/v1/tarefas", json={"titulo": "xxx", "setor_id": 1}, headers=ex).status_code == 403

    # IA sugere (não aplica sozinha)
    d = c.get(f"/api/v1/tarefas/{tid}", headers=ger).json()
    assert d["status"] == "NOVA" and d["ia_sugestao"]["estado"] == "pendente"
    top = d["ia_sugestao"]["classificacao"][0]
    assert top["categoria"] == "rede" and top["equipe"] == "TELECOM" and top["palavras"]
    assert d["origem"]["id"] == "9001"

    # 4) gestor confere a IA e atribui
    assert c.post(f"/api/v1/tarefas/{tid}/ia/decidir", json={"aceitar": True}, headers=ger).status_code == 200
    r = c.post(f"/api/v1/tarefas/{tid}/atribuir", json={"executor_ids": [exec3_id]}, headers=ger)
    assert r.status_code == 200 and r.json()["status"] == "ATRIBUIDA"
    # executor recebe notificação (push/inbox)
    n = c.get("/api/v1/notificacoes", headers=ex).json()
    assert any("missão" in x["titulo"].lower() and x["tarefa_id"] == tid for x in n["itens"])

    # permissões: outro executor não enxerga; gestor não executa
    outro = login(c, "exec1")
    assert c.get(f"/api/v1/tarefas/{tid}", headers=outro).status_code == 404
    assert c.post(f"/api/v1/tarefas/{tid}/iniciar", json={}, headers=ger).status_code == 403

    # 5-6) executor inicia, registra andamento, impedimento (material)
    assert c.post(f"/api/v1/tarefas/{tid}/iniciar", json={"lat": -25.53, "lon": -49.2}, headers=ex).json()["status"] == "EM_ANDAMENTO"
    assert c.post(f"/api/v1/tarefas/{tid}/andamento", data={"texto": "Cheguei, testando o cabo"}, headers=ex).status_code == 200
    r = c.post(f"/api/v1/tarefas/{tid}/impedimento", data={"tipo": "material",
               "descricao": "Falta patch cord de 3 metros para ligar o ponto"}, headers=ex)
    assert r.json()["status"] == "BLOQUEADA"
    notif_g = c.get("/api/v1/notificacoes", headers=ger).json()["itens"]
    assert any("Impedimento" in x["titulo"] for x in notif_g)
    # concluir bloqueada é proibido
    assert c.post(f"/api/v1/tarefas/{tid}/concluir", data={"descricao": "feito"}, headers=ex).status_code == 409
    # gestor trata o impedimento
    r = c.post(f"/api/v1/tarefas/{tid}/impedimento/resolver", json={"resolucao": "Cabo retirado no estoque"}, headers=ger)
    assert r.json()["status"] == "EM_ANDAMENTO"

    # tipo exige evidência: sem foto não conclui
    r = c.post(f"/api/v1/tarefas/{tid}/concluir", data={"descricao": "Ponto de rede religado e testado"}, headers=ex)
    assert r.status_code == 422 and "evidência" in r.json()["detail"]
    foto = ("foto.png", b"\x89PNG\r\n\x1a\nfake", "image/png")
    r = c.post(f"/api/v1/tarefas/{tid}/concluir", data={"descricao": "Ponto de rede religado e testado"},
               files=[("arquivos", foto)], headers=ex)
    assert r.status_code == 200 and r.json()["status"] == "CONCLUIDA_EXECUTOR"          # concluída ≠ resolvida
    assert r.json()["resolvido_em"] is None

    # 8) demandante: pendência → volta ao fluxo (e penaliza só se não houver impedimento externo)
    link = c.get(f"/api/v1/tarefas/{tid}", headers=ger).json()["link_validacao"]
    token = link.rsplit("/", 1)[1]
    assert c.get(f"/api/v1/validar/{token}").json()["evidencias"]
    r = c.post(f"/api/v1/validar/{token}", json={"resolvido": False, "motivo_pendencia": "O ponto continua sem sinal"})
    assert r.json()["status"] == "PENDENTE"
    assert c.get(f"/api/v1/validar/{token}").status_code == 404                            # link de uso único
    d = c.get(f"/api/v1/tarefas/{tid}", headers=ger).json()
    assert d["status"] == "PENDENTE" and d["reaberturas"] == 1

    # volta ao fluxo: gestor reatribui, novo ciclo e confirmação com nota
    assert c.post(f"/api/v1/tarefas/{tid}/atribuir", json={"executor_ids": [exec3_id]}, headers=ger).json()["status"] == "ATRIBUIDA"
    c.post(f"/api/v1/tarefas/{tid}/iniciar", json={}, headers=ex)
    c.post(f"/api/v1/tarefas/{tid}/concluir", data={"descricao": "Trocado o conector e refeito o teste"},
           files=[("arquivos", foto)], headers=ex)
    token2 = c.get(f"/api/v1/tarefas/{tid}", headers=ger).json()["link_validacao"].rsplit("/", 1)[1]
    assert c.post(f"/api/v1/validar/{token2}", json={"resolvido": True}).status_code == 422   # nota obrigatória
    r = c.post(f"/api/v1/validar/{token2}", json={"resolvido": True, "nota": 5, "comentario": "Funcionando"})
    assert r.status_code == 200
    d = c.get(f"/api/v1/tarefas/{tid}", headers=ger).json()
    assert d["status"] == "RESOLVIDA" and d["avaliacao"] == 5

    # 9) integração de saída: legado estava "fora do ar"? aqui está no ar (no_ar=False => 503)
    # → tudo fica pendente, ordenado; ao voltar, entrega tudo sem duplicar
    ob = c.get("/api/v1/integracao/outbox?limite=200", headers=ger).json()
    assert ob and all(o["status"] == "pendente" for o in ob if o["tarefa_id"] == tid)
    r = c.post("/api/v1/integracao/sincronizar", headers=ger).json()
    assert r["enviados"] == 0 and r["falhas"] >= 1                                      # falha temporária tolerada
    legado.no_ar = True                                                                  # legado volta
    r = c.post("/api/v1/integracao/sincronizar", headers=ger)
    for _ in range(30):                                                                  # ordem preservada: 1 por tarefa/rodada
        r = c.post("/api/v1/integracao/sincronizar", headers=ger)
        if r.json()["pendentes"] == 0:
            break
    assert r.json()["pendentes"] == 0
    msgs = sorted((m for m in legado.recebidas.values() if m["id_origem"] == "9001"), key=lambda m: m["sequencia"])
    assert [m["sequencia"] for m in msgs] == list(range(1, len(msgs) + 1))               # sem perda e em ordem
    assert msgs[0]["evento"] == "recebida" and msgs[-1]["status_legado"] == "CONCLUIDO"
    assert any(m["evento"] == "pendencia" and m["status_legado"] == "REABERTO" for m in msgs)
    assert any(m.get("impedimento") for m in msgs)
    assert all(m["id_origem"] == "9001" for m in msgs)                                    # vínculo com a origem

    # 10) gamificação: extrato explica cada ponto; qualidade e colaboração entram no cálculo
    ext = c.get(f"/api/v1/gamificacao/pontos?usuario_id={exec3_id}&limite=100", headers=ger).json()
    tipos = [e["tipo"] for e in ext if e["tarefa_id"] == tid]
    assert "conclusao" in tipos and "validacao" in tipos and "impedimento" in tipos and "reabertura" in tipos
    reab = next(e for e in ext if e["tarefa_id"] == tid and e["tipo"] == "reabertura")
    assert reab["pontos"] == 0 and "impedimento externo" in reab["explicacao"]           # bloqueio externo: sem penalidade
    val = next(e for e in ext if e["tarefa_id"] == tid and e["tipo"] == "validacao")
    assert val["pontos"] > 0 and "nota 5" in val["explicacao"]


def test_regras_e_reinicio_de_placar(c):
    ger, ex = login(c, "gestor"), login(c, "exec1")
    antes = c.get("/api/v1/gamificacao/ranking?acumulado=true", headers=ger).json()["itens"]
    total_antes = sum(i["pontos"] for i in antes)
    # regras ajustáveis pelo gestor; executor não pode
    assert c.put("/api/v1/gamificacao/regras", json={"regras": {"pontos_base": 120}}, headers=ex).status_code == 403
    r = c.put("/api/v1/gamificacao/regras", json={"regras": {"pontos_base": 120, "qualidade_por_nota": {"5": 1.5}}}, headers=ger)
    assert r.json()["regras"]["pontos_base"] == 120 and r.json()["regras"]["qualidade_por_nota"]["5"] == 1.5
    assert c.put("/api/v1/gamificacao/regras", json={"regras": {"fracao_na_conclusao": 3}}, headers=ger).status_code == 422
    # reinício do placar preserva o histórico
    per_antigo = c.get("/api/v1/gamificacao/ranking", headers=ger).json()["periodo"]["id"]
    novo = c.post("/api/v1/gamificacao/periodos/encerrar", json={"nome_proximo": "Teste"}, headers=ger).json()
    assert novo["historico_preservado"] is True
    atual = c.get("/api/v1/gamificacao/ranking", headers=ger).json()
    assert atual["periodo"]["nome"] == "Teste" and atual["itens"] == []                  # placar zerado
    hist = c.get(f"/api/v1/gamificacao/ranking?periodo_id={per_antigo}", headers=ger).json()["itens"]
    assert hist, "período anterior continua consultável"
    acum = c.get("/api/v1/gamificacao/ranking?acumulado=true", headers=ger).json()["itens"]
    assert sum(i["pontos"] for i in acum) == pytest.approx(total_antes)                  # nada foi apagado
    # ranking por equipe e por setor
    assert c.get("/api/v1/gamificacao/ranking?escopo=equipe&acumulado=true", headers=ger).json()["itens"]
    assert c.get("/api/v1/gamificacao/ranking?escopo=setor&acumulado=true", headers=ger).json()["itens"]


def test_generico_novo_setor_sem_legado(c):
    """Requisito 1: configurar setor/equipe/tipo novos e cadastrar tarefa direto na web."""
    adm = login(c, "admin")
    ger = login(c, "gestor")
    s = c.post("/api/v1/cadastros/setores", json={"nome": "Defesa Civil", "sigla": "DC"}, headers=adm).json()
    e = c.post("/api/v1/cadastros/equipes", json={"nome": "Vistoria de Risco", "setor_id": s["id"]}, headers=adm).json()
    t = c.post("/api/v1/cadastros/tipos", json={"nome": "Vistoria de encosta", "setor_id": s["id"], "equipe_padrao_id": e["id"],
               "complexidade": "alta", "exige_evidencia": True, "campos_obrigatorios": ["local"]}, headers=adm).json()
    at = login(c, "atendente1")
    r = c.post("/api/v1/tarefas", json={"titulo": "Encosta com trinca", "setor_id": s["id"], "tipo_id": t["id"]}, headers=at)
    assert r.status_code == 422 and "local" in r.json()["detail"]                        # campo obrigatório configurável
    r = c.post("/api/v1/tarefas", json={"titulo": "Encosta com trinca", "setor_id": s["id"], "tipo_id": t["id"],
               "local": "Rua das Flores 10", "descricao": "Moradores relatam trinca grande na encosta"}, headers=at)
    assert r.status_code == 201 and r.json()["equipe"] == "Vistoria de Risco" and r.json()["origem"] is None
    assert c.post("/api/v1/cadastros/setores", json={"nome": "X"}, headers=login(c, "exec1")).status_code == 403


def test_ia_previa_e_lacunas(c):
    at = login(c, "atendente1")
    r = c.post("/api/v1/ia/analisar", json={"titulo": "Telefone mudo", "descricao": "telefone mudo no setor sem tom",
                                            "unidade_demandante": "UPA Central"}, headers=at).json()
    assert r["classificacao"][0]["categoria"] == "telefonia"
    assert r["prioridade"]["valor"] == "alta" and r["prioridade"]["motivos"]
    assert any(l["campo"] == "contato" for l in r["lacunas"])                            # pergunta o ramal
    ger = login(c, "gestor")
    rec = c.get("/api/v1/ia/impedimentos-recorrentes", headers=ger).json()["itens"]
    assert rec and rec[0]["sugestao"]
    assert c.get("/api/v1/indicadores", headers=ger).json()["indicadores"]
