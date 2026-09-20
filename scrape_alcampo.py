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


def diagnose_category_page(html):
    print(f"DEBUG diagnóstico -> longitud del HTML: {len(html)} caracteres", file=sys.stderr)

    jsonld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    print(f"DEBUG diagnóstico -> bloques JSON-LD encontrados: {len(jsonld_blocks)}", file=sys.stderr)
    if jsonld_blocks:
        print(f"DEBUG diagnóstico -> primer bloque JSON-LD (800 caracteres): {jsonld_blocks[0][:800]}", file=sys.stderr)

    next_data = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    print(f"DEBUG diagnóstico -> ¿bloque __NEXT_DATA__ encontrado?: {next_data is not None}", file=sys.stderr)
    if next_data:
        print(f"DEBUG diagnóstico -> __NEXT_DATA__ (primeros 1000 caracteres): {next_data.group(1)[:1000]}", file=sys.stderr)

    # Busca cualquier otro <script> grande que contenga la palabra "price" o "precio",
    # señal de que ahí vive el estado inicial de la página con los productos.
    other_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    candidates = [s for s in other_scripts if ('"price"' in s or 'precio' in s.lower()) and len(s) > 500]
    print(f"DEBUG diagnóstico -> otros <script> grandes con 'price'/'precio': {len(candidates)}", file=sys.stderr)
    if candidates:
        print(f"DEBUG diagnóstico -> primer candidato (primeros 800 caracteres): {candidates[0][:800]}", file=sys.stderr)

    # Como último recurso, busca si aparecen precios en euros directamente en el HTML visible.
    price_like = re.findall(r'\d+[,.]\d{2}\s?€', html)
    print(f"DEBUG diagnóstico -> apariciones de 'X,XX €' en el HTML: {len(price_like)}", file=sys.stderr)
    if price_like:
        print(f"DEBUG diagnóstico -> ejemplos: {price_like[:10]}", file=sys.stderr)


def main():
    print(f"Probando con categoría de ejemplo: {SAMPLE_CATEGORY}", file=sys.stderr)
    html = fetch(SAMPLE_CATEGORY)

    if html is None:
        print("DEBUG -> la categoría de ejemplo no respondió con 200, revisa el log de arriba", file=sys.stderr)
    else:
        diagnose_category_page(html)

    # Salida provisional vacía: esta fase es solo de diagnóstico.
    output = {
        "store": "Alcampo",
        "region": "España",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": 0,
        "products": [],
        "note": "Fase de diagnóstico, sin productos todavía. Revisa el log DEBUG.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
