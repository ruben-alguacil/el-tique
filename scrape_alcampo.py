"""
Fase 1 (exploración) del scraper de Alcampo.

Alcampo no tiene una API abierta conocida, pero según scrapers ya existentes
del mercado, sus páginas de categoría (ej. compraonline.alcampo.es/categories/
leche-entera/OCEntera) se renderizan en el servidor, sin necesitar login ni
navegador. Sin poder probar en vivo, este script primero SOLO diagnostica:
encuentra una categoría real y cuenta qué formato usa para los datos de
producto (JSON-LD, un bloque JSON de Next.js, u otra cosa). Con ese reporte,
Claude escribe la extracción de verdad en la fase 2.

Uso: python scrape_alcampo.py > prices_alcampo.json
"""
import json
import re
import sys
import time
import requests

BASE = "https://www.compraonline.alcampo.es"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Categoría de ejemplo conocida (usada por otros scrapers), para arrancar el diagnóstico.
SAMPLE_CATEGORY = f"{BASE}/categories/leche-entera/OCEntera"


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    print(f"DEBUG fetch -> {url} status {r.status_code}", file=sys.stderr)
    if r.status_code != 200:
        print(f"DEBUG fetch -> cabeceras: {dict(r.headers)}", file=sys.stderr)
        print(f"DEBUG fetch -> primeros 500 caracteres: {r.text[:500]}", file=sys.stderr)
        return None
    return r.text


def extract_initial_state(html):
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx == -1:
        print("DEBUG -> no se encontró window.__INITIAL_STATE__ en esta página", file=sys.stderr)
        return None
    start = idx + len(marker)
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(html[start:])
    except json.JSONDecodeError as e:
        print(f"DEBUG -> fallo al parsear __INITIAL_STATE__ como JSON: {e}", file=sys.stderr)
        return None
    print("DEBUG -> __INITIAL_STATE__ parseado correctamente", file=sys.stderr)
    return data


def collect_dict_lists(obj, path="root", results=None):
    """Recorre el JSON y recopila TODAS las listas de diccionarios de tamaño >= 4,
    sin asumir ningún nombre de campo concreto."""
    if results is None:
        results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_dict_lists(v, f"{path}.{k}", results)
    elif isinstance(obj, list):
        if len(obj) >= 4 and isinstance(obj[0], dict):
            results.append((path, len(obj), obj[0]))
        for i, item in enumerate(obj[:5]):
            collect_dict_lists(item, f"{path}[{i}]", results)
    return results


def safe_get(obj, *path):
    for p in path:
        if isinstance(obj, dict):
            obj = obj.get(p)
        elif isinstance(obj, list) and isinstance(p, int):
            obj = obj[p] if -len(obj) <= p < len(obj) else None
        else:
            return None
    return obj


def parse_product(entity):
    price = entity.get("price", {}) or {}
    current = price.get("current", {}) or {}
    unit = (price.get("unit") or {}).get("current", {}) or {}
    return {
        "id": entity.get("productId"),
        "name": entity.get("name"),
        "brand": entity.get("brand"),
        "category": " > ".join(entity.get("categoryPath") or []),
        "price": float(current.get("amount")) if current.get("amount") else None,
        "currency": current.get("currency"),
        "reference_price": float(unit.get("amount")) if unit.get("amount") else None,
        "available": entity.get("available"),
    }


def collect_dict_of_dicts(obj, path="root", results=None):
    """Como collect_dict_lists, pero para diccionarios cuyos VALORES son diccionarios
    (mapas tipo {id: objeto}), que es como vino productEntities."""
    if results is None:
        results = []
    if isinstance(obj, dict):
        values = list(obj.values())
        if len(values) >= 4 and all(isinstance(v, dict) for v in values[:4]):
            results.append((path, len(obj), values[0]))
        for k, v in obj.items():
            collect_dict_of_dicts(v, f"{path}.{k}", results)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:5]):
            collect_dict_of_dicts(item, f"{path}[{i}]", results)
    return results


def main():
    print(f"Probando con categoría de ejemplo: {SAMPLE_CATEGORY}", file=sys.stderr)
    html = fetch(SAMPLE_CATEGORY)

    products_found = []
    if html is None:
        print("DEBUG -> la categoría de ejemplo no respondió con 200, revisa el log de arriba", file=sys.stderr)
    else:
        state = extract_initial_state(html)
        if state is not None:
            entities = safe_get(state, "data", "products", "productEntities")
            if isinstance(entities, dict):
                print(f"DEBUG entities -> productEntities tiene {len(entities)} productos", file=sys.stderr)
                products_found = [parse_product(e) for e in entities.values()]
                print(f"DEBUG entities -> ejemplo ya interpretado: {json.dumps(products_found[0], ensure_ascii=False)}", file=sys.stderr)

    # Ahora, por separado: diagnóstico de la página raíz de categorías, para
    # encontrar el árbol completo y no depender de una URL a mano.
    print("Probando con la página raíz de categorías", file=sys.stderr)
    root_html = fetch(f"{BASE}/categories")
    if root_html is not None:
        root_state = extract_initial_state(root_html)
        if root_state is not None:
            list_candidates = collect_dict_lists(root_state)
            list_candidates.sort(key=lambda c: c[1], reverse=True)
            print(f"DEBUG categorías -> {len(list_candidates)} listas de objetos encontradas", file=sys.stderr)
            for path, length, sample in list_candidates[:10]:
                print(f"DEBUG categorías lista -> {path} | elementos: {length} | claves: {list(sample.keys())}", file=sys.stderr)

            dict_candidates = collect_dict_of_dicts(root_state)
            dict_candidates.sort(key=lambda c: c[1], reverse=True)
            print(f"DEBUG categorías -> {len(dict_candidates)} diccionarios tipo mapa encontrados", file=sys.stderr)
            for path, length, sample in dict_candidates[:10]:
                print(f"DEBUG categorías mapa -> {path} | elementos: {length} | claves: {list(sample.keys())}", file=sys.stderr)

            # Candidatos con más probabilidad de ser el árbol de categorías: los que
            # tengan alguna clave relacionada con nombre/slug/url.
            print("DEBUG categorías -> buscando específicamente algo con 'categor' en la ruta", file=sys.stderr)
            for k in (root_state.get("data") or {}).keys():
                if "categ" in k.lower() or "nav" in k.lower() or "taxonomy" in k.lower():
                    print(f"DEBUG categorías -> clave interesante en data: '{k}'", file=sys.stderr)
                    print(f"DEBUG categorías -> contenido (1200 caracteres): {json.dumps(root_state['data'][k], ensure_ascii=False)[:1200]}", file=sys.stderr)

    output = {
        "store": "Alcampo",
        "region": "España",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": len(products_found),
        "products": products_found,
        "note": "Fase de diagnóstico de categorías, productos de una sola categoría de ejemplo.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
