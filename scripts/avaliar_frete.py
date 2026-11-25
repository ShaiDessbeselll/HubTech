"""Avalia a estimativa de FRETE da IA com os fretes reais que voce tem (validacao leave-one-out).

Para cada demanda com frete real, a IA estima o frete usando TODAS as outras e o erro e medido.
A linha de base e a media geral de R$/t x peso (estima sempre, sem criterio).

Rode na raiz do projeto:
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_frete.py --csv data\\rodomax_demandas.csv
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_frete.py --banco        (usa as demandas do HUB)
    adicione --min-casos 2 para aceitar estimar com menos casos (padrao: 3)

O arquivo precisa ter produto, origem, destino, peso e frete (os apelidos de coluna do HUB valem).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from ia import frete  # noqa: E402


def carregar(args):
    if args.csv:
        from core import importador as im
        caminho = Path(args.csv)
        return im.padronizar(im.ler_arquivo(caminho.name, caminho.read_bytes()))
    from core.db import consultar
    return pd.DataFrame(consultar("SELECT produto, origem, destino, peso_ton, frete FROM demandas "
                                  "WHERE frete IS NOT NULL"))


def brl(v):
    return "—" if v is None else "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v):
    return "—" if v is None else f"{v:.1%}"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="arquivo com o historico de fretes (csv, xlsx, json)")
    g.add_argument("--banco", action="store_true", help="usa as demandas do banco do HUB")
    ap.add_argument("--min-casos", type=int, default=frete.MIN_CASOS)
    args = ap.parse_args()

    df = carregar(args)
    r = frete.avaliar(df, args.min_casos)
    if r["n"] == 0:
        print("\nNenhuma demanda com frete e peso validos para avaliar.")
        return

    print(f"\n=== ESTIMATIVA DE FRETE — validacao leave-one-out — {r['n']} demandas com frete real ===")
    print(f"(a IA so estima com pelo menos {r['min_casos']} casos reais parecidos)\n")
    print(f"Cobertura: a IA estimou {r['n_estimados']} de {r['n']} ({r['cobertura']:.1%}); "
          f"nas demais ela se recusou a estimar por falta de base.")
    for nivel, q in r["niveis"].items():
        print(f"   - {q} pela {nivel}")
    if not r["n_estimados"]:
        print("\nSem casos estimados, nao ha erro para calcular. Isso e esperado com poucos dados.")
        return
    print(f"\nNos {r['n_estimados']} casos estimados:")
    print(f"   IA                       erro medio {brl(r['mae_ia']):>14}   erro percentual {pct(r['mape_ia'])}")
    print(f"   Linha de base (media/t)  erro medio {brl(r['mae_base_mesmos']):>14}   "
          f"erro percentual {pct(r['mape_base_mesmos'])}")
    print(f"\nLinha de base em TODOS os {r['n']} casos: erro medio {brl(r['mae_base_todos'])}, "
          f"erro percentual {pct(r['mape_base_todos'])}")


if __name__ == "__main__":
    main()
