"""Gera data/baseline_helpdesk.json: números AGREGADOS do Help Desk real (sem nomes, sem texto de chamados).
Uso: python scripts/gerar_baseline.py caminho/chamados.csv   (colunas: abertura, fechamento, status, setor)
Sem CSV, grava um PLACEHOLDER explícito (sem números inventados)."""
import csv, json, sys, statistics as st
from datetime import datetime
from pathlib import Path

SAIDA = Path(__file__).resolve().parent.parent / "data" / "baseline_helpdesk.json"

def dt(s):
    for f in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try: return datetime.strptime(s.strip(), f)
        except Exception: pass

def main():
    if len(sys.argv) < 2:
        out = {"origem": "placeholder", "aviso": "Sem dados reais carregados. Exporte os chamados do Help Desk (sem dados pessoais) e rode: python scripts/gerar_baseline.py chamados.csv"}
    else:
        tempos, status, setores = [], {}, {}
        for r in csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")):
            a, f = dt(r.get("abertura", "")), dt(r.get("fechamento", ""))
            if a and f and f >= a: tempos.append((f - a).total_seconds() / 3600)
            status[r.get("status", "?")] = status.get(r.get("status", "?"), 0) + 1
            setores[r.get("setor", "?")] = setores.get(r.get("setor", "?"), 0) + 1
        out = {"origem": "csv_real_agregado", "chamados": sum(status.values()), "por_status": status, "por_setor": setores,
               "horas_ate_fechamento": {"mediana": round(st.median(tempos), 1), "p90": round(st.quantiles(tempos, n=10)[-1], 1), "n": len(tempos)} if len(tempos) > 10 else None}
    SAIDA.parent.mkdir(exist_ok=True); SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=2)); print("gravado", SAIDA)

main()
