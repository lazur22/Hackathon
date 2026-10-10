"""Apoio à demonstração (Bancada): reinicia os dados FICTÍCIOS para repetir o roteiro do início."""
from __future__ import annotations
from fastapi import APIRouter

from ..config import DEMO_RESET
from ..db import Base, SessionLocal, engine, garantir_colunas
from ..seed import semear
from ..services.erros import ErroNegocio

router = APIRouter(prefix="/api/v1/demo", tags=["Demonstração"])


@router.post("/reiniciar")
def reiniciar():
    """Apaga e recria o banco com os dados de demonstração. Só funciona com DEMO_RESET=1 (padrão do protótipo)."""
    if not DEMO_RESET:
        raise ErroNegocio("Reinício da demonstração desativado neste ambiente.", 403)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    garantir_colunas()
    with SessionLocal() as db:
        semear(db)
    return {"ok": True}


@router.get("/estado")
def estado():
    return {"demo": True, "reiniciar_ativo": DEMO_RESET}
