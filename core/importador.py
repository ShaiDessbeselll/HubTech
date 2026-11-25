"""RF01-RF06: leitura, extração, validação, limpeza, deduplicação e gravação."""
import hashlib
import io
import json
import re
from datetime import date, timedelta

import pandas as pd

from core.auth import registrar_log
from core.crm import calcular_prioridade, formatar_brl
from core.db import get_conn
from ia.modulo import estimar_frete

COLUNAS = ["produto", "origem", "destino", "peso_ton", "prazo", "frete"]
OBRIGATORIAS = ["produto", "origem", "destino", "peso_ton"]

# nomes alternativos de colunas encontrados em fontes diferentes
ALIASES = {
    "produto": ["produto", "carga", "mercadoria", "item", "descricao"],
    "origem": ["origem", "cidade_origem", "coleta", "de", "from"],
    "destino": ["destino", "cidade_destino", "entrega", "para", "to"],
    "peso_ton": ["peso_ton", "peso", "toneladas", "ton", "peso_kg", "qtd"],
    "prazo": ["prazo", "data_entrega", "data", "entrega_ate", "deadline"],
    "frete": ["frete", "valor", "valor_frete", "preco", "preço"],
}


# ---------- leitura por tipo de arquivo ----------
def ler_arquivo(nome, conteudo: bytes) -> pd.DataFrame:
    ext = nome.lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xls"):
        return pd.read_excel(io.BytesIO(conteudo), dtype=str)
    if ext == "csv":
        txt = conteudo.decode("utf-8-sig", errors="replace")
        sep = ";" if txt.count(";") > txt.count(",") else ","
        return pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
    if ext == "json":
        dados = json.loads(conteudo.decode("utf-8-sig"))
        if isinstance(dados, dict):
            dados = dados.get("demandas") or dados.get("data") or [dados]
        return pd.json_normalize(dados).astype(str)
    if ext == "pdf":
        return _ler_pdf(conteudo)
    if ext == "txt":
        return _ler_texto(conteudo.decode("utf-8", errors="replace"))
    raise ValueError(f"Formato não suportado: .{ext}")


def _ler_pdf(conteudo):
    import pdfplumber
    linhas, texto = [], ""
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pag in pdf.pages:
            for tabela in pag.extract_tables():
                if tabela and len(tabela) > 1:
                    cab = [str(c or "").strip() for c in tabela[0]]
                    for row in tabela[1:]:
                        linhas.append(dict(zip(cab, row)))
            texto += (pag.extract_text() or "") + "\n"
    if linhas:
        return pd.DataFrame(linhas).astype(str)
    return _ler_texto(texto)


def _extrair_livre(b):
    """Mensagem livre: 'Preciso levar 28 toneladas de soja de Cascavel para Paranaguá até 25/11'."""
    reg = {}
    m = re.search(r"(\d[\d\.,]*)\s*(toneladas?|tons?|t|kg|quilos?)\b", b, flags=re.I)
    if m:
        reg["peso_ton"] = f"{m.group(1)} {m.group(2)}"
        m2 = re.search(r"\b(?:de|do|da)\s+([A-Za-zÀ-ú]+(?: [A-Za-zÀ-ú]+)?)\s+(?:saindo|de|da|do|em|para|pra)\b",
                       b[m.end():], flags=re.I)
        if m2:
            reg["produto"] = m2.group(1).strip()
    m = re.search(r"\b(?:de|da|do|saindo de)\s+([A-ZÀ-Ú][\wÀ-ú]*(?: [A-ZÀ-Ú][\wÀ-ú]*)*)\s+"
                  r"(?:para|pra|até|ate|a)\s+([A-ZÀ-Ú][\wÀ-ú]*(?: [A-ZÀ-Ú][\wÀ-ú]*)*)", b)
    if m:
        reg["origem"], reg["destino"] = m.group(1).strip(), m.group(2).strip()
    m = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", b)
    if m:
        reg["prazo"] = m.group(1)
    m = re.search(r"R\$\s*([\d\.,]+(?:\s*mil)?)", b, flags=re.I) or \
        re.search(r"(?:frete|valor)\s*(?:de\s*)?([\d\.,]+\s*mil)\b", b, flags=re.I)
    if m:
        reg["frete"] = m.group(1)
    return reg


def _ler_texto(texto):
    """Extração por regex de mensagens livres (WhatsApp/e-mail). Cada bloco separado por
    linha em branco vira uma demanda. Espaço para o módulo de IA/NLP complementar."""
    padrao = {
        "produto": r"(?:produto|carga|mercadoria)\s*[:\-]\s*([^\n,;]+)",
        "origem": r"(?:origem|coleta)\s*[:\-]\s*([^\n,;]+)",
        "destino": r"(?:destino|entrega)\s*[:\-]\s*([^\n,;]+)",
        "peso_ton": r"(?:peso)\s*[:\-]\s*([\d\.,]+\s*(?:kg|t|ton|toneladas)?)",
        "prazo": r"(?:prazo|data)\s*[:\-]\s*([\d/\-]+)",
        "frete": r"(?:frete|valor)\s*[:\-]\s*(?:R\$)?\s*([\d\.,]+(?:\s*mil)?)",
    }
    blocos = [b for b in re.split(r"\n\s*\n", texto) if b.strip()]
    linhas = []
    for b in blocos:
        reg = {}
        for campo, rx in padrao.items():
            m = re.search(rx, b, flags=re.I)
            if m:
                reg[campo] = m.group(1).strip()
        for campo, valor in _extrair_livre(b).items():  # completa o que faltou
            reg.setdefault(campo, valor)
        if reg:
            linhas.append(reg)
    return pd.DataFrame(linhas)


# ---------- padronização ----------
def _num_br(v):
    if v is None or str(v).strip() in ("", "nan", "None"):
        return None
    s = re.sub(r"[^\d,\.\-]", "", str(v))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _peso_ton(v):
    bruto = str(v).lower()
    n = _num_br(v)
    if n is None:
        return None
    if "kg" in bruto or (n > 100 and "t" not in bruto):  # 28000 -> 28 t
        n = n / 1000
    return round(n, 2)


def _frete(v):
    """Aceita 'R$ 9.800,00', '9800' e '7 mil' (= 7000)."""
    n = _num_br(v)
    if n is not None and re.search(r"\bmil\b", str(v).lower()):
        n *= 1000
    return n


def _prazo(v):
    """Converte o prazo em data. Sem ano ('30/11'), assume o ano atual (ou o próximo, se a data
    já passou há mais de 30 dias). Valor que não é data ('urgente', 'sexta') vira vazio."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in ("", "nan", "none", "nat"):
        return None
    sem_ano = re.fullmatch(r"\d{1,2}[/\-]\d{1,2}", s)
    if sem_ano:
        s = f"{s}/{date.today().year}"
    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(d) or d.year < 2000:
        return None
    d = d.date()
    if sem_ano and d < date.today() - timedelta(days=30):
        d = d.replace(year=d.year + 1)
    return d


def _texto(v):
    if v is None or str(v).strip().lower() in ("", "nan", "none"):
        return None
    palavras = " ".join(str(v).split()).title().split()
    peq = {"De", "Do", "Da", "Dos", "Das", "E"}
    return " ".join(p.lower() if (i > 0 and p in peq) else p for i, p in enumerate(palavras))


def padronizar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns]
    mapa = {}
    for padrao, apelidos in ALIASES.items():
        for c in df.columns:
            if c in apelidos and padrao not in mapa.values():
                mapa[c] = padrao
                break
    df = df.rename(columns=mapa)
    for c in COLUNAS:
        if c not in df.columns:
            df[c] = None
    df = df[COLUNAS].copy()
    for c in ("produto", "origem", "destino"):
        df[c] = df[c].map(_texto)
    df["peso_ton"] = df["peso_ton"].map(_peso_ton)
    df["frete"] = df["frete"].map(_frete)
    df["prazo"] = df["prazo"].map(_prazo)
    return df


def _estimar_frete(r, frete):
    """Se o frete veio vazio, pede uma sugestão ao módulo de IA (ia/modulo.py::estimar_frete).
    Uma falha da IA nunca derruba a importação: a demanda só fica sem estimativa."""
    if frete is not None:
        return None
    try:
        v = estimar_frete(dict(produto=r["produto"], origem=r["origem"], destino=r["destino"],
                               peso_ton=r["peso_ton"],
                               prazo=None if pd.isna(r["prazo"]) else str(r["prazo"])))
        return None if v is None else round(float(v), 2)
    except Exception:
        return None


def _hash(r):
    prazo = "NaT" if pd.isna(r["prazo"]) else str(r["prazo"])
    base = "|".join([str(r[c]) for c in ("produto", "origem", "destino", "peso_ton")] + [prazo])
    return hashlib.sha256(base.encode()).hexdigest()


def validar(r):
    faltando = [c for c in OBRIGATORIAS if r[c] is None or pd.isna(r[c])]
    if faltando:
        return "Campos ausentes: " + ", ".join(faltando)
    if r["peso_ton"] <= 0 or r["peso_ton"] > 60:
        return f"Peso inválido: {r['peso_ton']} t"
    if r["origem"] == r["destino"]:
        return "Origem igual ao destino"
    return None


# ---------- pipeline completo ----------
def importar(usuario_id, nome_arquivo, conteudo, origem):
    return _processar(usuario_id, nome_arquivo, ler_arquivo(nome_arquivo, conteudo), origem)


def importar_texto(usuario_id, texto, origem):
    """Importa texto colado na tela (um ou vários blocos separados por linha em branco)."""
    bruto = _ler_texto(texto)
    if bruto.empty:
        raise ValueError("Não encontrei nenhuma informação de frete no texto colado.")
    return _processar(usuario_id, "texto_colado", bruto, origem)


def _processar(usuario_id, nome_arquivo, bruto, origem):
    df = padronizar(bruto)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO importacoes (usuario_id, nome_arquivo, origem, qtd_lidos, status) "
            "VALUES (%s,%s,%s,%s,'PROCESSANDO')",
            (usuario_id, nome_arquivo, origem, len(df)),
        )
        imp_id = cur.lastrowid
        ok = dup = rej = 0
        for i, r in df.iterrows():
            erro = validar(r)
            if erro:
                rej += 1
                cur.execute(
                    "INSERT INTO registros_rejeitados (importacao_id, linha, motivo, conteudo) "
                    "VALUES (%s,%s,%s,%s)",
                    (imp_id, int(i) + 2, erro, r.to_json(force_ascii=False, date_format="iso")),
                )
                continue
            prazo = None if pd.isna(r["prazo"]) else r["prazo"]
            frete = None if pd.isna(r["frete"]) else r["frete"]
            estimado = _estimar_frete(r, frete)
            try:
                # entra no CRM: status NOVA, prioridade pelo prazo, responsável = quem importou
                cur.execute(
                    "INSERT INTO demandas (importacao_id, produto, origem, destino, peso_ton, prazo, "
                    "frete, frete_estimado, hash_registro, status, prioridade, responsavel_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'NOVA',%s,%s)",
                    (imp_id, r["produto"], r["origem"], r["destino"], r["peso_ton"], prazo, frete,
                     estimado, _hash(r), calcular_prioridade(prazo), usuario_id),
                )
                demanda_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, para_valor, texto) "
                    "VALUES (%s,%s,'CRIACAO','Nova',%s)",
                    (demanda_id, usuario_id,
                     f"Criada automaticamente pela importação #{imp_id} ({origem}, {nome_arquivo})"),
                )
                if estimado is not None:
                    cur.execute(
                        "INSERT INTO demanda_historico (demanda_id, usuario_id, tipo, texto) "
                        "VALUES (%s,%s,'IA',%s)",
                        (demanda_id, usuario_id, f"IA sugeriu o frete em R$ {formatar_brl(estimado)}"),
                    )
                ok += 1
            except Exception as e:  # chave duplicada (RF05)
                if getattr(e, "errno", None) == 1062:
                    dup += 1
                    # guarda o duplicado (com o id da demanda que já existia) para consulta no Histórico
                    cur.execute("SELECT id FROM demandas WHERE hash_registro=%s", (_hash(r),))
                    ja = cur.fetchone()
                    cur.execute(
                        "INSERT INTO registros_rejeitados (importacao_id, linha, motivo, conteudo) "
                        "VALUES (%s,%s,%s,%s)",
                        (imp_id, int(i) + 2,
                         f"DUPLICADO: já existe a demanda #{ja[0] if ja else '?'}",
                         r.to_json(force_ascii=False, date_format="iso")))
                else:
                    raise
        status = "CONCLUIDA" if ok else "SEM_REGISTROS_NOVOS"
        cur.execute(
            "UPDATE importacoes SET qtd_registros=%s, qtd_duplicados=%s, qtd_rejeitados=%s, "
            "status=%s WHERE id=%s", (ok, dup, rej, status, imp_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    registrar_log(usuario_id, "IMPORTACAO",
                  f"{nome_arquivo} | origem={origem} | ok={ok} dup={dup} rej={rej}")
    return {"importacao_id": imp_id, "lidos": len(df), "ok": ok, "duplicados": dup, "rejeitados": rej}
