"""OS digital, rotas por proximidade, assistente que aprende com as OS e indicadores de confiabilidade."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/t2.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/up"
os.environ["OUTBOX_INTERVALO_S"] = "3600"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cli:
        yield cli


def H(c, login):
    t = c.post("/api/v1/auth/login", json={"login": login, "senha": "demo123"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def test_os_digital_responde_as_perguntas_do_papel(c):
    g = H(c, "gestor")
    ts = c.get("/api/v1/tarefas?status=RESOLVIDA", headers=g).json()
    assert ts
    o = c.get(f"/api/v1/tarefas/{ts[0]['id']}/os", headers=g).json()
    for campo in ("quando", "quem", "como", "o_que_foi_feito", "pendencias", "fotos", "selo_integridade", "equipamento"):
        assert campo in o
    assert o["quando"]["tempo_de_reparo_min"] is not None
    assert len(o["selo_integridade"]) == 64
    assert o["o_que_foi_feito"] and "N/D" not in o["o_que_foi_feito"]
    # o selo é determinístico (rastreabilidade): consultar duas vezes dá o mesmo hash
    assert c.get(f"/api/v1/tarefas/{ts[0]['id']}/os", headers=g).json()["selo_integridade"] == o["selo_integridade"]


def test_rota_perto_de_voce_sem_voltar_a_central(c):
    ex = H(c, "exec3")
    r = c.get("/api/v1/rota/proximas?lat=-25.5700&lon=-49.1850", headers=ex).json()
    assert r["origem"] == "posição atual"
    kms = [p["km"] for p in r["sequencia"]]
    assert r["sequencia"] and all(k >= 0 for k in kms)
    g = H(c, "gestor")
    res = c.get("/api/v1/rota/resumo", headers=g).json()
    assert res["economia"]["km_digital"] <= res["economia"]["km_papel"]
    assert res["central"]["central"] is True


def test_assistente_aprende_com_os_resolvidas_e_feedback(c):
    a = H(c, "atendente1")
    r = c.post("/api/v1/chat", json={"mensagem": "telefone mudo sem tom de linha no ramal"}, headers=a).json()
    assert r["confianca"] in ("alta", "media") and r["fontes"]
    assert "cabo" in r["resposta"].lower()
    assert any(f["tipo"] == "os" for f in r["fontes"]), "deve citar OS já resolvidas, não só a base de conhecimento"
    c.post(f"/api/v1/chat/{r['conversa_id']}/feedback", json={"resolveu": True}, headers=a)
    # pergunta fora do conhecimento: admite que não sabe e pergunta o que falta
    r2 = c.post("/api/v1/chat", json={"mensagem": "xyzzy plugh qwerty"}, headers=a).json()
    assert r2["confianca"] == "baixa"
    g = H(c, "gestor")
    resumo = c.get("/api/v1/chat/resumo", headers=g).json()
    assert resumo["taxa_deflexao"] == 100.0 and resumo["lacunas_de_conhecimento"]
    # gestor ensina: o conhecimento novo passa a ser encontrado
    c.post("/api/v1/chat/conhecimento", json={"titulo": "Catraca da recepção travada", "sintomas": "catraca travada recepcao cartao de acesso",
                                                "passos": ["Reinicie o leitor de cartão.", "Verifique a fonte da catraca."]}, headers=g)
    r3 = c.post("/api/v1/chat", json={"mensagem": "a catraca da recepção está travada"}, headers=a).json()
    assert "leitor" in r3["resposta"].lower()
    # novas OS resolvidas entram no índice (retroalimentação): similares aparece no painel do atendente
    s = c.post("/api/v1/ia/analisar", json={"titulo": "Telefone mudo no cemitério", "descricao": "sem tom de linha"}, headers=a).json()
    assert s["similares"]


def test_indicadores_mttr_mtbf_recorrencia_avaliacao(c):
    g = H(c, "gestor")
    d = c.get("/api/v1/indicadores/confiabilidade", headers=g).json()
    assert d["mttr"]["horas_media"] is not None and d["mttr"]["amostra"] > 5
    assert d["mtbf"]["ativos_com_reincidencia"] >= 2 and d["mtbf"]["dias_media"] > 0
    assert d["recorrencia"]["os_recorrentes"] >= 1
    assert d["avaliacoes"]["media"] and sum(d["avaliacoes"]["distribuicao"].values()) == d["avaliacoes"]["amostra"]
    assert d["os_abertas"]["ultimos_30_dias"] >= 1
