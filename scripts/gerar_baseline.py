"""Gera data/baseline_helpdesk.json a partir do export do Help Desk (chamadosAAAAMMDD.txt, colunas largura fixa).
Saída AGREGADA: sem nomes de pessoas, sem texto de chamados. Uso: python scripts/gerar_baseline.py caminho/chamados.txt"""
import collections, json, statistics as st, sys
from datetime import datetime
from pathlib import Path

SAIDA = Path(__file__).resolve().parent.parent / "data" / "baseline_helpdesk.json"
COLS = ["COD_CHAMADO", "ANO_CHAMADO", "COD_ODD_SOL", "DPTO_SOLICITANTE", "DPTO_RESPONSAVEL", "USUCOD_TECNICO", "USUANOME",
        "DESCR_STATUS", "DATA_ABERTURA", "DATA_FINAL"]


def dt(s):
    try:
        return datetime.strptime(s.strip()[:17], "%d.%m.%y %H:%M:%S")
    except Exception:
        return None


def ler(caminho):
    bruto = Path(caminho).read_bytes()
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252", errors="replace")   # export do legado costuma ser Windows-1252
    linhas = texto.splitlines()
    pos = [linhas[0].index(c) for c in COLS]
    for l in linhas[1:]:
        if l.strip():
            yield {c: l[pos[i]:(pos[i + 1] if i + 1 < len(pos) else None)].strip() for i, c in enumerate(COLS)}


def main():
    if len(sys.argv) < 2:
        SAIDA.write_text(json.dumps({"origem": "placeholder", "aviso": "Rode: python scripts/gerar_baseline.py chamados.txt"}, ensure_ascii=False, indent=2))
        print("placeholder gravado"); return
    rows = list(ler(sys.argv[1]))
    horas = []
    for r in rows:
        a, f = dt(r["DATA_ABERTURA"]), dt(r["DATA_FINAL"])
        if r["DESCR_STATUS"] == "CONCLUIDO" and a and f and f >= a:
            horas.append((f - a).total_seconds() / 3600)
    por_mes = collections.Counter(dt(r["DATA_ABERTURA"]).strftime("%Y-%m") for r in rows if dt(r["DATA_ABERTURA"]))
    q = st.quantiles(horas, n=10)
    sem_tec = sum(1 for r in rows if not r["USUANOME"])
    out = {
        "origem": "export_helpdesk_agregado", "periodo": f"{min(por_mes)} a {max(por_mes)}", "chamados": len(rows),
        "por_status": dict(collections.Counter(r["DESCR_STATUS"] for r in rows)),
        "por_departamento_responsavel": dict(collections.Counter(r["DPTO_RESPONSAVEL"] for r in rows).most_common(8)),
        "por_mes": dict(sorted(por_mes.items())),
        "horas_ate_conclusao": {"mediana": round(st.median(horas), 1), "media": round(st.mean(horas), 1), "p90": round(q[-1], 1), "n": len(horas)},
        "percentual_conclusao_acima_de_72h": round(100 * sum(1 for h in horas if h > 72) / len(horas), 1),
        "percentual_sem_nome_de_tecnico_no_registro": round(100 * sem_tec / len(rows), 1),
        "leitura": "Linha de base REAL do Help Desk antes da plataforma (dados agregados, sem dados pessoais).",
    }
    SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=2)); print(json.dumps(out, ensure_ascii=False, indent=1)[:900])


main()
