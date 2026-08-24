import json, hashlib, os, time
from datetime import datetime, timedelta, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import yaml

ROOT = os.path.dirname(os.path.dirname(__file__))
NOV = os.path.join(ROOT, "data", "novidades.json")
SRC = os.path.join(os.path.dirname(__file__), "sources.yaml")
TZ = timezone(timedelta(hours=-3))

def agora():
    return datetime.now(TZ)

def now_str():
    return agora().strftime("%Y-%m-%d %H:%M")

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sha(s):
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:16]

def criar_sessao():
    """Sessão HTTP com retry automático para erros de servidor (502/503/504) e timeout."""
    sessao = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,  # espera 2s, 4s, 8s entre tentativas
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    return sessao

SESSAO = criar_sessao()

def aplicar_placeholders(url, extra=None):
    """Troca {ano}, {mes}, {mesAnterior}, {anoMesAnterior}, {hoje}, {ha30dias} e chaves extras na URL."""
    hoje = agora()
    ha30 = hoje - timedelta(days=30)

    mes_anterior = hoje.month - 1
    ano_mes_anterior = hoje.year
    if mes_anterior == 0:
        mes_anterior = 12
        ano_mes_anterior -= 1

    subs = {
        "{ano}": str(hoje.year),
        "{mes}": str(hoje.month),
        "{mesAnterior}": str(mes_anterior),
        "{anoMesAnterior}": str(ano_mes_anterior),
        "{hoje}": hoje.strftime("%Y%m%d"),
        "{ha30dias}": ha30.strftime("%Y%m%d"),
    }
    if extra:
        subs.update(extra)
    for k, v in subs.items():
        url = url.replace(k, str(v))
    return url

def get_field(obj, path, default=""):
    if not path:
        return default
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def extract_list(payload):
    """Tenta achar a lista de registros dentro de formatos comuns de API."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        chaves_possiveis = [
            "data", "itens", "registros", "results", "content",
            "despesas", "receitas", "resultado", "resultados",
            "lista", "edicoes", "docs", "items"
        ]
        for key in chaves_possiveis:
            if key in payload and isinstance(payload[key], list):
                return payload[key]
    return []

def debug_estrutura(payload, nome):
    """Imprime a estrutura da resposta quando não encontramos registros — ajuda a corrigir o mapeamento."""
    if isinstance(payload, dict):
        print(f"     [DEBUG {nome}] Resposta é um objeto (dict) com chaves: {list(payload.keys())[:15]}")
        amostra = json.dumps(payload, ensure_ascii=False)[:400]
        print(f"     [DEBUG {nome}] Amostra: {amostra}")
    elif isinstance(payload, list):
        print(f"     [DEBUG {nome}] Resposta é uma lista com {len(payload)} itens (mas veio vazia ou não reconhecida)")
    else:
        print(f"     [DEBUG {nome}] Tipo inesperado: {type(payload)}")

def montar_itens(registros, campos, nome_fonte, url_base):
    itens = []
    for reg in registros:
        if not isinstance(reg, dict):
            continue
        titulo = str(get_field(reg, campos.get("titulo"), "")).strip()
        if not titulo or titulo.lower() in ("item", "sem título", "none"):
            continue
        data_pub = get_field(reg, campos.get("data"), "")
        link = get_field(reg, campos.get("link"), "") or url_base
        valor = get_field(reg, campos.get("valor"), "")
        id_raw = get_field(reg, campos.get("id"), titulo)

        resumo = ""
        if valor not in ("", None):
            try:
                resumo = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                resumo = "Valor: R$ " + resumo
            except Exception:
                resumo = f"Valor: {valor}"

        itens.append({
            "id": sha(f"{nome_fonte}-{id_raw}"),
            "titulo": titulo[:200],
            "link": str(link),
            "resumo": resumo,
            "data": str(data_pub)[:19],
            "fonte": nome_fonte
        })
    return itens

def fetch_api_json(fonte):
    nome = fonte.get("nome", "sem nome")
    campos = fonte.get("campos", {})
    url_template = fonte["url"]
    variacoes = fonte.get("variacoes", [None])

    todos = []
    for var in variacoes:
        extra = {"{variacao}": var} if var is not None else None
        url = aplicar_placeholders(url_template, extra)
        try:
            r = SESSAO.get(url, timeout=(10, 50), headers={
                "User-Agent": "Mozilla/5.0 (compatible; acorda-sbo/1.0; +cidadania)",
                "Accept": "application/json"
            })
            if r.status_code == 204:
                print(f"[OK-VAZIO] {nome} (var={var}): sem registros (204)")
                continue
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            print(f"[FALHA] {nome} (var={var}): {e}")
            print(f"         URL: {url}")
            continue

        registros = extract_list(payload)
        print(f"[OK] {nome} (var={var}): {len(registros)} registros brutos")

        if registros:
            if len(todos) == 0:
                print(f"     Exemplo de chaves disponíveis: {list(registros[0].keys())[:12]}")
        else:
            debug_estrutura(payload, nome)

        todos.extend(montar_itens(registros, campos, nome, url))
        time.sleep(1.5)

    return todos

def fetch_html_list(fonte):
    nome = fonte.get("nome", "sem nome")
    url = aplicar_placeholders(fonte["url"])
    selector = fonte["selector"]
    base = fonte.get("base", "")
    try:
        r = SESSAO.get(url, timeout=(10, 50), headers={"User-Agent": "Mozilla/5.0 (compatible; acorda-sbo/1.0)"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[FALHA] {nome}: {e}")
        return []

    out = []
    vistos = set()
    for a in soup.select(selector):
        titulo = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if not titulo or len(titulo) < 4:
            continue
        if base and href.startswith("/"):
            href = base.rstrip("/") + href
        chave = href or titulo
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append({
            "id": sha(f"{nome}-{chave}"),
            "titulo": titulo[:200],
            "link": href or url,
            "resumo": "",
            "data": agora().strftime("%Y-%m-%d %H:%M"),
            "fonte": nome
        })
    print(f"[OK] {nome}: {len(out)} itens coletados")
    return out

def main():
    cfg = yaml.safe_load(open(SRC, "r", encoding="utf-8"))
    store = load_json(NOV, {"ultima_atualizacao": "", "itens": []})
    known = {it["id"] for it in store.get("itens", [])}

    print("=" * 60)
    print(f"COLETA INICIADA — {now_str()}")
    print("=" * 60)

    novos = []

    for fonte in cfg.get("api_json", []):
        for it in fetch_api_json(fonte):
            if it["id"] not in known:
                novos.append(it)
                known.add(it["id"])

    for fonte in cfg.get("html", []):
        for it in fetch_html_list(fonte):
            if it["id"] not in known:
                novos.append(it)
                known.add(it["id"])
        time.sleep(1)

    print("=" * 60)
    print(f"RESULTADO: {len(novos)} itens novos")
    print("=" * 60)

    if novos:
        todos = novos + store.get("itens", [])
        todos = sorted(todos, key=lambda x: x.get("data", ""), reverse=True)[:500]
        store["itens"] = todos

    store["ultima_atualizacao"] = now_str()
    save_json(NOV, store)

if __name__ == "__main__":
    main()
