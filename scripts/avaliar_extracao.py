"""Avalia a EXTRACAO de campos (produto, origem, destino, peso, prazo, frete) de mensagens livres.

Compara o resultado de cada metodo com o gabarito de data/mensagens_teste.json e calcula a
taxa de acerto por campo, a taxa de mensagens 100% corretas e o desempenho por nivel/tipo.

Rode na raiz do projeto:
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_extracao.py                 (linha de base: regex)
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_extracao.py --metodo nlp    (regras + spaCy)
    .\\.venv\\Scripts\\python.exe scripts\\avaliar_extracao.py --metodo todos  (tabela comparativa)
    adicione --erros para ver cada campo errado

Nao precisa de banco de dados.
"""
import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core import importador as im  # noqa: E402
from ia import extrator  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent
CAMPOS = ["produto", "origem", "destino", "peso_ton", "prazo", "frete"]


# ---------- metodos de extracao (cada um recebe o texto e devolve um dict com os 6 campos) ----------
def extrair_regex(texto, data_ref=None):
    """LINHA DE BASE: o extrator por expressoes regulares que ja existe no HUBTECH."""
    df = im.padronizar(im._ler_texto(texto))
    if df.empty:
        return {c: None for c in CAMPOS}
    r = df.iloc[0]
    saida = {}
    for c in CAMPOS:
        v = r[c]
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            saida[c] = None
        elif c == "prazo":
            saida[c] = str(v)
        else:
            saida[c] = v
    return saida


def extrair_regras(texto, data_ref=None):
    """PLN so com regras linguisticas (sem spaCy): datas relativas, frete informal, contexto."""
    return extrator.extrair(texto, data_ref, usar_spacy=False)


def extrair_nlp(texto, data_ref=None):
    """PLN completo: regras + NER do spaCy (se estiver instalado)."""
    return extrator.extrair(texto, data_ref, usar_spacy=True)


CONJ = {"teste": "mensagens_teste", "validacao": "mensagens_validacao"}
METODOS = {"regex": extrair_regex, "regras": extrair_regras, "nlp": extrair_nlp}


# ---------- comparacao ----------
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def igual(campo, previsto, esperado):
    if esperado is None or previsto is None:
        return esperado is None and previsto is None
    if campo in ("peso_ton", "frete"):
        return abs(float(previsto) - float(esperado)) < 0.01
    if campo == "prazo":
        return str(previsto) == str(esperado)
    return _norm(previsto) == _norm(esperado)


def avaliar(metodo, conjunto="mensagens_teste"):
    dados = json.loads((PASTA / "data" / f"{conjunto}.json").read_text(encoding="utf-8"))
    data_ref = dados["data_referencia"]
    funcao = METODOS[metodo]

    acertos = {c: 0 for c in CAMPOS}
    perfeitas = 0
    por_grupo = defaultdict(lambda: [0, 0])  # grupo -> [mensagens perfeitas, total]
    erros = []

    msgs = dados["mensagens"]
    for m in msgs:
        try:
            prev = funcao(m["texto"], data_ref)
        except Exception as e:  # um erro do metodo conta como tudo errado
            prev = {c: None for c in CAMPOS}
            erros.append((m["id"], "ERRO", repr(e), ""))
        tudo_certo = True
        for c in CAMPOS:
            ok = igual(c, prev.get(c), m["gabarito"][c])
            acertos[c] += ok
            if not ok:
                tudo_certo = False
                erros.append((m["id"], c, prev.get(c), m["gabarito"][c]))
        perfeitas += tudo_certo
        for g in (f"nivel: {m['nivel']}", f"tipo: {m['tipo']}" if m.get("tipo") else None):
            if g:
                por_grupo[g][0] += tudo_certo
                por_grupo[g][1] += 1
    return len(msgs), acertos, perfeitas, por_grupo, erros


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metodo", default="regex", choices=list(METODOS) + ["todos"])
    ap.add_argument("--conjunto", default="teste", choices=["teste", "validacao"],
                    help="teste = mensagens usadas no desenvolvimento; validacao = mensagens NOVAS")
    ap.add_argument("--erros", action="store_true", help="lista cada campo errado")
    args = ap.parse_args()

    if args.metodo in ("nlp", "todos"):
        ok, motivo = extrator.status_spacy()
        if not ok:
            print(f"\n[AVISO] spaCy NAO carregou ({motivo}).\n"
                  "        O metodo 'nlp' vai rodar so com as regras (igual ao 'regras').\n"
                  "        Instale:  python -m pip install spacy  e  "
                  "python -m spacy download pt_core_news_sm")

    if args.metodo == "todos":
        return comparar(CONJ[args.conjunto])

    n, acertos, perfeitas, por_grupo, erros = avaliar(args.metodo, CONJ[args.conjunto])

    print(f"\n=== EXTRACAO — metodo: {args.metodo} — conjunto: {args.conjunto} — {n} mensagens ===\n")
    print("Acerto por campo:")
    for c in CAMPOS:
        print(f"  {c:<10} {acertos[c]:>3}/{n}  {acertos[c] / n:6.1%}")
    media = sum(acertos.values()) / (n * len(CAMPOS))
    print(f"\n  Media dos campos:             {media:6.1%}")
    print(f"  Mensagens 100% corretas:      {perfeitas}/{n}  {perfeitas / n:6.1%}")

    print("\nMensagens 100% corretas por grupo:")
    for g in sorted(por_grupo):
        ok, tot = por_grupo[g]
        print(f"  {g:<28} {ok:>2}/{tot:<2}  {ok / tot:6.1%}")

    if args.erros:
        print("\nErros (id | campo | previsto | esperado):")
        for i, c, p, e in erros:
            print(f"  #{i:<3} {c:<9} previsto={p!r:<28} esperado={e!r}")
    else:
        print("\n(use --erros para ver cada campo errado)")


def comparar(conjunto):
    print(f"\n{'metodo':<8}" + "".join(f"{c:>10}" for c in CAMPOS) + f"{'media':>9}{'msgs 100%':>12}")
    for nome in METODOS:
        n, acertos, perfeitas, _g, _e = avaliar(nome, conjunto)
        media = sum(acertos.values()) / (n * len(CAMPOS))
        linha = "".join(f"{acertos[c] / n:>10.1%}" for c in CAMPOS)
        print(f"{nome:<8}{linha}{media:>9.1%}{perfeitas / n:>12.1%}")
    print(f"\n({n} mensagens, conjunto: {conjunto})")


if __name__ == "__main__":
    main()
