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


PRODUCT_KEY_HINTS = {"price", "name", "title", "sku", "productid", "unitprice"}


def find_product_lists(obj, path="root", results=None, max_results=6):
    """Recorre el JSON buscando listas de diccionarios que parezcan productos."""
    if results is None:
        results = []
    if len(results) >= max_results:
        return results

    if isinstance(obj, dict):
        for k, v in obj.items():
            find_product_lists(v, f"{path}.{k}", results, max_results)
    elif isinstance(obj, list) and obj:
        sample = obj[0]
        if isinstance(sample, dict):
            keys_lower = {k.lower() for k in sample.keys()}
            hits = keys_lower & PRODUCT_KEY_HINTS
            if len(hits) >= 2:
                results.append((path, len(obj), list(sample.keys())[:15], sample))
        # sigue bajando también dentro de listas, por si hay listas anidadas
        for item in obj[:5]:
            find_product_lists(item, f"{path}[]", results, max_results)
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
            candidates = find_product_lists(state)
            print(f"DEBUG -> {len(candidates)} listas candidatas a 'productos' encontradas", file=sys.stderr)
            for path, length, keys, sample in candidates:
                print(f"DEBUG candidato -> ruta: {path} | elementos: {length} | claves: {keys}", file=sys.stderr)
                print(f"DEBUG candidato -> ejemplo completo: {json.dumps(sample, ensure_ascii=False)[:1000]}", file=sys.stderr)

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
