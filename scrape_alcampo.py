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
                first_key = next(iter(entities))
                print(f"DEBUG entities -> ejemplo completo de un producto: {json.dumps(entities[first_key], ensure_ascii=False)[:2000]}", file=sys.stderr)
            else:
                print("DEBUG entities -> no se encontró data.products.productEntities como diccionario", file=sys.stderr)

            groups = safe_get(state, "data", "products", "catalogue", "data", "productGroups")
            if isinstance(groups, list):
                print(f"DEBUG groups -> productGroups tiene {len(groups)} grupos", file=sys.stderr)
                for i, g in enumerate(groups):
                    if isinstance(g, dict):
                        keys = list(g.keys())
                        print(f"DEBUG groups -> grupo {i} claves: {keys}", file=sys.stderr)
                        # imprime el grupo entero salvo el campo ya visto (additionalProductAttributes)
                        g_copy = {k: v for k, v in g.items() if k != "additionalProductAttributes"}
                        print(f"DEBUG groups -> grupo {i} contenido (sin additionalProductAttributes, 1500 caracteres): {json.dumps(g_copy, ensure_ascii=False)[:1500]}", file=sys.stderr)
            else:
                print("DEBUG groups -> no se encontró productGroups como lista", file=sys.stderr)

    # Salida provisional vacía: esta fase es solo de diagnóstico.
    output = {
        "store": "Alcampo",
        "region": "España",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": len(products_found),
        "products": products_found,
        "note": "Fase de diagnóstico, sin productos todavía. Revisa el log DEBUG.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
