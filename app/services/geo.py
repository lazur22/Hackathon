"""Geografia operacional: distância, atendimento por proximidade e economia estimada de deslocamento.
As coordenadas dos locais cadastrados na demonstração são APROXIMADAS/FICTÍCIAS; em produção, geocodificar o endereço
(ou usar o GPS registrado ao iniciar o atendimento). Distância em linha reta × fator de 1,35 ≈ distância por vias."""
from __future__ import annotations
import math
import unicodedata
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Local, Tarefa

FATOR_VIAS = 1.35          # linha reta -> distância aproximada pelas ruas
VEL_URBANA_KMH = 30.0
CUSTO_KM = 1.20            # R$/km (premissa configurável; só para estimativa)


def _n(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h)) * FATOR_VIAS


def central(db: Session) -> Optional[Local]:
    return db.scalar(select(Local).where(Local.central.is_(True)))


def resolver_local(db: Session, *textos: str) -> Optional[Local]:
    """Casa texto livre (local, unidade, título) com um local cadastrado — pelo nome ou por apelidos."""
    alvo = _n(" | ".join(t for t in textos if t))
    if not alvo.strip():
        return None
    melhor, tam = None, 0
    for l in db.scalars(select(Local).where(Local.ativo.is_(True), Local.central.is_(False))).all():
        for nome in [l.nome, *(l.aliases or [])]:
            n = _n(nome)
            if n and n in alvo and len(n) > tam:
                melhor, tam = l, len(n)
    return melhor


def aplicar_local(db: Session, t: Tarefa) -> None:
    l = resolver_local(db, t.local, t.unidade_demandante, t.titulo, t.descricao)
    if l:
        t.local_id, t.lat, t.lon = l.id, l.lat, l.lon
        if not t.secretaria and l.secretaria:
            t.secretaria = l.secretaria


def ponto(t: Tarefa) -> Optional[tuple[float, float]]:
    return (t.lat, t.lon) if t.lat is not None and t.lon is not None else None


def rota_vizinho_mais_proximo(origem: tuple[float, float], tarefas: list[Tarefa]) -> list[dict]:
    """Ordena atendimentos: urgentes/altas primeiro quando estão a até 6 km a mais que o vizinho mais próximo;
    caso contrário, o mais próximo do ponto atual. Devolve a sequência com a distância de cada trecho."""
    restantes = [t for t in tarefas if ponto(t)]
    seq, atual = [], origem
    peso = {"urgente": 6.0, "alta": 3.0, "normal": 0.0, "baixa": -1.0}
    while restantes:
        proximo = min(restantes, key=lambda t: haversine(atual, ponto(t)) - peso.get(t.prioridade, 0.0))
        d = haversine(atual, ponto(proximo))
        seq.append({"tarefa": proximo, "km": round(d, 1), "min": round(60 * d / VEL_URBANA_KMH)})
        atual = ponto(proximo)
        restantes.remove(proximo)
    return seq


def comprimento(origem: tuple[float, float], sequencia: list[Tarefa], voltar: bool) -> float:
    km, atual = 0.0, origem
    for t in sequencia:
        km += haversine(atual, ponto(t)); atual = ponto(t)
    return km + (haversine(atual, origem) if voltar else 0.0)


def economia(base: tuple[float, float], tarefas_por_tecnico: dict[int, list[Tarefa]]) -> dict:
    """Papel: após cada OS o técnico volta à central (ida e volta por tarefa). Digital: encadeia pela proximidade e
    volta uma vez só ao final. ESTIMATIVA com os atendimentos que estão abertos agora — não é medição."""
    papel = digital = 0.0
    por_tecnico = []
    for uid, ts in tarefas_por_tecnico.items():
        ts = [t for t in ts if ponto(t)]
        if not ts:
            continue
        a = sum(2 * haversine(base, ponto(t)) for t in ts)
        seq = [x["tarefa"] for x in rota_vizinho_mais_proximo(base, ts)]
        b = comprimento(base, seq, voltar=True)
        papel += a; digital += min(a, b)
        por_tecnico.append({"usuario_id": uid, "atendimentos": len(ts), "km_papel": round(a, 1), "km_digital": round(min(a, b), 1)})
    eco = papel - digital
    return {"km_papel": round(papel, 1), "km_digital": round(digital, 1), "km_economizados": round(eco, 1),
            "percentual": round(100 * eco / papel, 1) if papel else 0.0, "custo_estimado_economizado": round(eco * CUSTO_KM, 2),
            "premissas": f"linha reta × {FATOR_VIAS} (vias), R$ {CUSTO_KM:.2f}/km; estimativa sobre atendimentos abertos agora",
            "por_tecnico": por_tecnico}
