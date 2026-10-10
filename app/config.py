"""Configuração por variáveis de ambiente. Nenhum serviço externo é obrigatório (soberania digital)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'missao.db'}")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
SESSAO_HORAS = int(os.getenv("SESSAO_HORAS", "12"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# IA local opcional (Ollama roda no próprio datacenter). Sem ela, a IA usa modelos locais leves
# (Naive Bayes + regras) e continua funcionando 100% offline.
OLLAMA_URL = os.getenv("OLLAMA_URL", "")            # ex.: http://ollama:11434
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# Integração com o legado simulado
OUTBOX_INTERVALO_S = float(os.getenv("OUTBOX_INTERVALO_S", "3"))

# Web Push (opcional; exige HTTPS fora do localhost). Chaves VAPID geradas no 1º start se ausentes.
VAPID_FILE = BASE_DIR / "data" / "vapid.json"
VAPID_CONTATO = os.getenv("VAPID_CONTATO", "mailto:simot@sjp.pr.gov.br")

SEED_ON_START = os.getenv("SEED_ON_START", "1") == "1"

# Demonstração: permite reiniciar os dados fictícios pela tela "Bancada" (desligue com DEMO_RESET=0 fora de demos).
DEMO_RESET = os.getenv("DEMO_RESET", "1") == "1"
