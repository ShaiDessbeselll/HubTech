"""Extracao de demandas de frete a partir de mensagens livres (PLN) - 2a etapa do trabalho.

Recebe um texto de WhatsApp/e-mail e devolve os 6 campos do HUB:
    produto, origem, destino, peso_ton, prazo (AAAA-MM-DD), frete

Como funciona (regras linguisticas + modelo de linguagem):
  * PESO    - numero + unidade ("28 t", "30 mil quilos", "1,5 toneladas", "vinte toneladas").
  * PRAZO   - data explicita OU expressao relativa resolvida pela data da mensagem
              ("ate sexta", "amanha", "dia 28", "fim do mes", "em 3 dias", "semana que vem").
  * FRETE   - "R$ 9.800,00", "uns 10 mil", "pago 6k", "6.400 reais"; "a combinar" = vazio.
  * LUGARES - candidatos vindos de (1) lista de cidades conhecidas, (2) NER do spaCy e
              (3) palavras com inicial maiuscula depois de preposicao. Quem e ORIGEM e quem e
              DESTINO e decidido pelo CONTEXTO ("de X para Y", "coleta em X", "destino: Y").
  * PRODUTO - rotulo ("Produto: Soja"), lista de cargas conhecidas ou palavra apos o peso.

O spaCy e OPCIONAL: sem ele o extrator funciona so com as regras (usar_spacy=False).
Instalacao:  python -m pip install spacy
             python -m spacy download pt_core_news_sm

Teste rapido:  python -m ia.extrator "Preciso levar 20 t de milho de Toledo para Maringa ate sexta"
"""
import calendar
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta

CAMPOS = ["produto", "origem", "destino", "peso_ton", "prazo", "frete"]

# ---------------------------------------------------------------------------------------------
# Listas de apoio (conhecimento do dominio)
# ---------------------------------------------------------------------------------------------
CIDADES = [
    "Cascavel", "Toledo", "Maringá", "Londrina", "Curitiba", "Paranaguá", "Ponta Grossa",
    "Foz do Iguaçu", "Guarapuava", "Campo Mourão", "Umuarama", "Francisco Beltrão", "Pato Branco",
    "Medianeira", "Marechal Cândido Rondon", "Palotina", "Assis Chateaubriand", "Guaíra",
    "Apucarana", "Arapongas", "Cianorte", "Paranavaí", "Telêmaco Borba", "Irati",
    "União da Vitória", "Castro", "Lapa", "São José dos Pinhais", "Araucária", "Joinville",
    "Florianópolis", "Itajaí", "Chapecó", "Blumenau", "Porto Alegre", "Pelotas", "Passo Fundo",
    "Santa Maria", "Rio Grande", "Caxias do Sul", "São Paulo", "Santos", "Campinas",
    "Ribeirão Preto", "Sorriso", "Rondonópolis", "Cuiabá", "Lucas do Rio Verde", "Sinop",
    "Campo Grande", "Dourados", "Rio Verde", "Goiânia", "Uberlândia", "Belo Horizonte",
    "Rio de Janeiro", "Brasília", "Salvador", "Vitória", "Maracaju", "Primavera do Leste",
]

PRODUTOS = [
    "Soja", "Milho", "Trigo", "Arroz", "Feijão", "Café", "Açúcar", "Fertilizante", "Adubo",
    "Calcário", "Cimento", "Madeira", "Sementes", "Farelo de Soja", "Farelo de Milho",
    "Óleo de Soja", "Algodão", "Cana", "Areia", "Brita", "Ração", "Carne", "Frango", "Leite",
    "Aço", "Sorgo", "Cevada", "Aveia", "Calcário Agrícola", "Cal", "Sal", "Soja em Grão",
]

_NAO_LUGAR = {
    "bom", "boa", "ola", "pessoal", "preciso", "tenho", "tem", "carga", "produto", "origem",
    "destino", "frete", "valor", "prazo", "peso", "coleta", "entrega", "data", "mercadoria",
    "urgente", "brasil", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo",
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro", "pr", "sp", "sc", "rs", "mt", "ms", "go", "mg",
}

_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4,
                "sabado": 5, "domingo": 6}

_NUM_EXTENSO = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50, "sessenta": 60,
}


# ---------------------------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------------------------
def _norm(s):
    """Minusculas e sem acentos, MANTENDO o mesmo comprimento (posicoes iguais as do original)."""
    saida = []
    for ch in str(s):
        base = unicodedata.normalize("NFKD", ch)[:1] or ch
        saida.append(base.lower()[:1] or ch)
    return "".join(saida)


def _titulo(v):
    palavras = " ".join(str(v).split()).title().split()
    peq = {"De", "Do", "Da", "Dos", "Das", "E"}
    return " ".join(p.lower() if (i > 0 and p in peq) else p for i, p in enumerate(palavras))


def _num(s):
    """'9.800,00' -> 9800.0 | '11.200' -> 11200.0 | '1,5' -> 1.5 | '28' -> 28.0"""
    s = str(s).strip().rstrip(".,")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")
    return float(s)


def _como_data(v):
    if v is None:
        return date.today()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _lexico(itens):
    mapa = {_norm(i): i for i in itens}
    rx = re.compile(r"(?<![a-z0-9])(" + "|".join(
        re.escape(k) for k in sorted(mapa, key=len, reverse=True)) + r")(?![a-z0-9])")
    return mapa, rx


_CID, _CID_RX = _lexico(CIDADES)
_PROD, _PROD_RX = _lexico(PRODUTOS)


# ---------------------------------------------------------------------------------------------
# spaCy (opcional)
# ---------------------------------------------------------------------------------------------
_NLP = None
_ERRO_SPACY = None


def _carregar_spacy():
    global _NLP, _ERRO_SPACY
    if _NLP is None and _ERRO_SPACY is None:
        try:
            import spacy
            _NLP = spacy.load("pt_core_news_sm")
        except Exception as e:  # spaCy ou o modelo nao instalado
            _ERRO_SPACY = f"{type(e).__name__}: {e}"
    return _NLP


def status_spacy():
    """(True, None) se o spaCy carregou; (False, motivo) se nao."""
    _carregar_spacy()
    return _NLP is not None, _ERRO_SPACY


# ---------------------------------------------------------------------------------------------
# PESO
# ---------------------------------------------------------------------------------------------
_UN_PESO = r"(?:toneladas?|tons?|ton|t|quilos?|kilos?|kg)"
_PESO_DIG = re.compile(r"(?<![\d/.,])(\d[\d.,]*)\s*(mil\s+)?(" + _UN_PESO + r")\b")
_PALAVRAS = "|".join(sorted(_NUM_EXTENSO, key=len, reverse=True))
_PESO_EXT = re.compile(
    r"\b((?:vinte|trinta|quarenta|cinquenta|sessenta)(?:\s+e\s+(?:um|dois|tres|quatro|cinco|seis|"
    r"sete|oito|nove))?|" + _PALAVRAS + r")\s+(toneladas?|tons?|ton)\b")
_PESO_ROTULO = re.compile(r"\bpeso\s*[:\-]?\s*(\d[\d.,]*)")


def _peso(nt):
    """-> (toneladas, (ini, fim)) ou (None, None)"""
    m = _PESO_DIG.search(nt)
    if m:
        n = _num(m.group(1))
        if m.group(2):
            n *= 1000
        if m.group(3).startswith(("kg", "quilo", "kilo")):
            n /= 1000
        return round(n, 2), m.span()
    m = _PESO_EXT.search(nt)
    if m:
        return float(sum(_NUM_EXTENSO[p] for p in m.group(1).split() if p != "e")), m.span()
    m = _PESO_ROTULO.search(nt)
    if m:
        n = _num(m.group(1))
        return round(n / 1000 if n > 100 else n, 2), m.span()
    return None, None


# ---------------------------------------------------------------------------------------------
# PRAZO
# ---------------------------------------------------------------------------------------------
_DATA_ANO = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)")
_DATA_CURTA = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
_REL_AMANHA2 = re.compile(r"\bdepois de amanha\b")
_REL_AMANHA = re.compile(r"\bamanha\b")
_REL_HOJE = re.compile(r"\bhoje\b")
_REL_SEMANA_FIM = re.compile(r"\b(?:fim|final) da semana (?:que vem|seguinte|proxima)\b")
_REL_SEMANA = re.compile(r"\b(?:semana que vem|proxima semana|semana seguinte)\b")
_REL_FIM_MES = re.compile(r"\b(?:fim|final) do mes\b")
_REL_EM_DIAS = re.compile(r"\b(?:em|daqui a|dentro de)\s+(\d{1,3})\s+dias?\b")
_REL_DIA_N = re.compile(r"\b(?:ate|para|pra|no|em)\s+(?:o\s+)?dia\s+(\d{1,2})\b(?!\s*/)")
_REL_SEMANA_DIA = re.compile(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?\b")


def _data_valida(ano, mes, dia):
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _prazo(nt, ref):
    """-> (date | None). Datas explicitas primeiro; depois expressoes relativas a `ref`."""
    m = _DATA_ANO.search(nt)
    if m:
        ano = int(m.group(3))
        ano += 2000 if ano < 100 else 0
        return _data_valida(ano, int(m.group(2)), int(m.group(1)))
    m = _DATA_CURTA.search(nt)
    if m:
        d = _data_valida(ref.year, int(m.group(2)), int(m.group(1)))
        if d and d < ref - timedelta(days=30):  # sem ano e ja passou: e do ano seguinte
            d = _data_valida(ref.year + 1, int(m.group(2)), int(m.group(1)))
        return d
    if _REL_AMANHA2.search(nt):
        return ref + timedelta(days=2)
    if _REL_AMANHA.search(nt):
        return ref + timedelta(days=1)
    if _REL_HOJE.search(nt):
        return ref
    segunda_que_vem = ref + timedelta(days=7 - ref.weekday())
    if _REL_SEMANA_FIM.search(nt):
        return segunda_que_vem + timedelta(days=4)
    if _REL_SEMANA.search(nt):
        return segunda_que_vem
    if _REL_FIM_MES.search(nt):
        return date(ref.year, ref.month, calendar.monthrange(ref.year, ref.month)[1])
    m = _REL_EM_DIAS.search(nt)
    if m:
        return ref + timedelta(days=int(m.group(1)))
    m = _REL_DIA_N.search(nt)
    if m:
        dia = int(m.group(1))
        d = _data_valida(ref.year, ref.month, dia)
        if d is None or d < ref:  # "dia 5" dito no fim do mes = mes seguinte
            ano, mes = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
            d = _data_valida(ano, mes, dia)
        return d
    m = _REL_SEMANA_DIA.search(nt)
    if m:  # proxima ocorrencia (estritamente depois de hoje)
        alvo = _DIAS_SEMANA[m.group(1)]
        return ref + timedelta(days=((alvo - ref.weekday() - 1) % 7) + 1)
    return None


# ---------------------------------------------------------------------------------------------
# FRETE
# ---------------------------------------------------------------------------------------------
_F_RS = re.compile(r"r\$\s*(\d[\d.,]*)(?:\s*(mil|k)\b)?")
_F_CUE = re.compile(
    r"\b(?:frete|valor|pago|paga|pagamos|ofereco|oferta|pagaria)\s*[:\-]?\s*"
    r"(?:(?:de|em torno de|cerca de|uns|umas|aproximadamente|r\$)\s*)*"
    r"(\d[\d.,]*)\s*(mil|k)?\b")
_F_MIL_ANTES = re.compile(r"(\d[\d.,]*)\s*(mil|k)\s*(?:de\s+|do\s+)?(?:frete|valor)\b")
_F_APROX = re.compile(
    r"\b(?:uns|umas|cerca de|aproximadamente|em torno de)\s+(\d[\d.,]*)\s*(mil|k)\b")
_F_REAIS = re.compile(r"(\d[\d.,]*)\s*(?:reais|conto|contos)\b")


def _frete(nt_limpo):
    """nt_limpo = texto sem os trechos de peso e de data (para nao confundir os numeros)."""
    for rx in (_F_RS, _F_CUE, _F_MIL_ANTES, _F_APROX, _F_REAIS):
        m = rx.search(nt_limpo)
        if m:
            try:
                n = _num(m.group(1))
            except ValueError:
                continue
            sufixo = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            if sufixo:
                n *= 1000
            return round(n, 2)
    return None


# ---------------------------------------------------------------------------------------------
# PRODUTO
# ---------------------------------------------------------------------------------------------
_ROTULOS = r"(?:produto|carga|mercadoria|origem|destino|peso|prazo|frete|valor|data|coleta|entrega|retirada)"
_P_ROTULO = re.compile(r"(?:produto|carga|mercadoria)[ \t]*[:\-][ \t]*"
                       r"([^\n,;]+?)(?=[ \t]+" + _ROTULOS + r"[ \t]*[:\-]|[\n,;]|$)")
_P_APOS_PESO = re.compile(r"(?:toneladas?|tons?|ton|t|quilos?|kilos?|kg)\s+de\s+([a-z]+)\b")


def _produto(texto, nt):
    m = _P_ROTULO.search(nt)
    if m:
        bruto = texto[m.start(1):m.end(1)].strip()
        return _PROD.get(_norm(bruto)) or _titulo(bruto)
    achados = [(x.end() - x.start(), -x.start(), x) for x in _PROD_RX.finditer(nt)]
    if achados:
        return _PROD[max(achados)[2].group(1)]
    m = _P_APOS_PESO.search(nt)
    if m:
        return _titulo(texto[m.start(1):m.end(1)])
    return None


# ---------------------------------------------------------------------------------------------
# ORIGEM e DESTINO
# ---------------------------------------------------------------------------------------------
_NAO_CAP = r"(?!(?:Produto|Carga|Mercadoria|Origem|Destino|Peso|Prazo|Frete|Valor|Data|Coleta|Entrega|Retirada)\b)"
_CAP = _NAO_CAP + r"[A-ZÀ-Ý][a-zà-ÿ]+"
_NOME_CAP = _CAP + r"(?:[ \t]+(?:de|do|da|dos|das|e)[ \t]+" + _CAP + r"|[ \t]+" + _CAP + r")*"
_L_PREP = re.compile(r"\b(?i:de|do|da|para|pra|em|a|até|ate|x)[ \t]+(" + _NOME_CAP + r")")
_L_ROTULO = re.compile(r"\b(?i:origem|destino|coleta|entrega|retirada)[ \t]*[:\-][ \t]*("
                       + _NOME_CAP + r")")

_CUE_O1 = re.compile(r"(?:origem|colet\w*|retir\w*|busc\w*|saind\w*|partind\w*)"
                     r"(?:\s+(?:em|de|da|do|na|no))?\s*[:\-]?\s*$")
_CUE_D1 = re.compile(r"(?:destino|entreg\w*|rumo|chegar|chegando|descarreg\w*)"
                     r"(?:\s+(?:em|a|ao|para|na|no|de))?\s*[:\-]?\s*$")
_CUE_D2 = re.compile(r"(?:\bpara|\bpra|\bate|\ba|\bao|\bx|>|\s-)\s*$")
_CUE_O2 = re.compile(r"(?:\bde|\bdo|\bda|\bem|\bno|\bna)\s*$")


def _eh_lugar_valido(nome):
    n = _norm(nome).strip()
    if not n or n in _PROD or n.split()[0] in _NAO_LUGAR:
        return False
    return True


def _candidatos_lugar(texto, nt, nlp):
    cands = []  # (ini, fim, nome, prioridade) - menor prioridade vence empate de tamanho
    for m in _CID_RX.finditer(nt):
        cands.append((m.start(), m.end(), _CID[m.group(1)], 0))
    if nlp is not None:
        for ent in nlp(texto).ents:
            if ent.label_ in ("LOC", "GPE"):
                txt = ent.text.split("/")[0].strip()
                if txt and txt[0].isupper() and _eh_lugar_valido(txt):
                    cands.append((ent.start_char, ent.start_char + len(txt), _titulo(txt), 1))
    for rx in (_L_ROTULO, _L_PREP):
        for m in rx.finditer(texto):
            if _eh_lugar_valido(m.group(1)):
                cands.append((m.start(1), m.end(1), _titulo(m.group(1)), 2))
    # escolhe sem sobreposicao: trechos maiores primeiro (ex.: "Foz do Iguacu" ganha de "Iguacu")
    escolhidos = []
    for c in sorted(cands, key=lambda c: (-(c[1] - c[0]), c[3])):
        if all(c[1] <= e[0] or c[0] >= e[1] for e in escolhidos):
            escolhidos.append(c)
    return sorted(escolhidos)


def _funcao_do_lugar(ctx):
    if _CUE_O1.search(ctx):
        return "O"
    if _CUE_D1.search(ctx):
        return "D"
    if _CUE_D2.search(ctx):
        return "D"
    if _CUE_O2.search(ctx):
        return "O"
    return None


def _origem_destino(texto, nt, nlp):
    lugares = [(i, n, _funcao_do_lugar(nt[max(0, i - 40):i]))
               for i, _f, n, _p in _candidatos_lugar(texto, nt, nlp)]
    origem = next((x for x in lugares if x[2] == "O"), None)
    destino = next((x for x in lugares if x[2] == "D" and x is not origem), None)
    livres = [x for x in lugares if x[2] is None and x is not origem and x is not destino]
    if origem is None and livres:
        origem = livres.pop(0)
    if destino is None and livres:
        destino = livres.pop(0)
    if destino is None:  # ultimo recurso: qualquer outro lugar citado
        destino = next((x for x in lugares if x is not origem), None)
    if origem is None:
        origem = next((x for x in lugares if x is not destino), None)
    return (origem[1] if origem else None), (destino[1] if destino else None)


# ---------------------------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------------------------
def extrair(texto, data_ref=None, usar_spacy=True):
    """Extrai os campos de UMA mensagem. data_ref = data em que a mensagem chegou (para
    resolver 'sexta', 'amanha'...). Sem data_ref usa hoje."""
    ref = _como_data(data_ref)
    nt = _norm(texto)
    nlp = _carregar_spacy() if usar_spacy else None

    peso, span_peso = _peso(nt)

    limpo = list(nt)  # sem peso e sem datas, para o frete nao confundir numeros
    trechos = [span_peso] if span_peso else []
    trechos += [m.span() for rx in (_DATA_ANO, _DATA_CURTA) for m in rx.finditer(nt)]
    for ini, fim in trechos:
        limpo[ini:fim] = " " * (fim - ini)
    frete = _frete("".join(limpo))

    prazo = _prazo(nt, ref)
    origem, destino = _origem_destino(texto, nt, nlp)
    return {
        "produto": _produto(texto, nt),
        "origem": origem,
        "destino": destino,
        "peso_ton": peso,
        "prazo": prazo.isoformat() if prazo else None,
        "frete": frete,
    }


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "Preciso levar 20 t de milho de Toledo para Maringá até sexta, uns 6 mil"
    ok, erro = status_spacy()
    print(f"spaCy: {'ativo' if ok else 'NAO carregado (' + str(erro) + ')'}")
    for k, v in extrair(msg).items():
        print(f"  {k:<9} {v}")