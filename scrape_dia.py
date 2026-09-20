"""
Descarga precios de Dia.es leyendo:
1. Su mapa del sitio (sitemap.xml), para encontrar URLs de productos.
2. Los datos estructurados (JSON-LD, tipo "Product") que casi toda tienda
   online incrusta en cada página de producto para que Google la lea.

Dia no publica una API abierta como Mercadona, así que este método es más
lento (una petición por producto) y depende de que Dia siga usando esa
ficha de datos estándar. Si algo falla, pega el log de "DEBUG" a Claude.

Uso: python scrape_dia.py > prices_dia.json
"""
import json
import re
import sys
import time
import requests
from xml.etree import ElementTree

BASE = "https://www.dia.es"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
MAX_PRODUCTS = 300  # límite para la primera prueba; se sube luego si todo funciona


def get_sitemap_urls(sitemap_url, depth=0):
    """Recorre sitemap.xml (o índices de sitemaps) y devuelve URLs de producto."""
    if depth > 2:
        return []
    r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
    print(f"DEBUG sitemap -> {sitemap_url} status {r.status_code}", file=sys.stderr)
    if r.status_code != 200:
        print(f"DEBUG sitemap -> cabeceras de la respuesta: {dict(r.headers)}", file=sys.stderr)
        print(f"DEBUG sitemap -> primeros 500 caracteres del cuerpo: {r.text[:500]}", file=sys.stderr)
        return []
    try:
        root = ElementTree.fromstring(r.content)
    except ElementTree.ParseError as e:
        print(f"DEBUG sitemap -> no se pudo parsear XML: {e}", file=sys.stderr)
        print(f"DEBUG sitemap -> primeros 500 caracteres: {r.text[:500]}", file=sys.stderr)
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text for el in root.findall(".//sm:loc", ns)]
    print(f"DEBUG sitemap -> {len(locs)} URLs encontradas en {sitemap_url}", file=sys.stderr)
    if locs:
        print(f"DEBUG sitemap -> primeras 3: {locs[:3]}", file=sys.stderr)

    product_urls = [u for u in locs if "/p/" in u]
    if product_urls:
        return product_urls

    # Si no son URLs de producto directamente, puede que sean sub-sitemaps
    sub_sitemaps = [u for u in locs if u.endswith(".xml")]
    all_products = []
    for sm in sub_sitemaps[:20]:  # límite de seguridad
        all_products.extend(get_sitemap_urls(sm, depth=depth + 1))
        time.sleep(0.3)
    return all_products


def extract_jsonld_product(html, url):
    """Busca un bloque <script type="application/ld+json"> con datos de producto."""
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") in ("Product", ["Product"]):
                return item
    return None


def parse_product(jsonld, url):
    offers = jsonld.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    return {
        "name": jsonld.get("name"),
        "brand": (jsonld.get("brand") or {}).get("name") if isinstance(jsonld.get("brand"), dict) else jsonld.get("brand"),
        "price": price,
        "currency": offers.get("priceCurrency"),
        "sku": jsonld.get("sku"),
        "url": url,
    }


def main():
    product_urls = get_sitemap_urls(f"{BASE}/sitemap.xml")
    print(f"Total de URLs de producto encontradas: {len(product_urls)}", file=sys.stderr)

    if not product_urls:
        print("DEBUG -> no se encontraron URLs de producto, revisa el log de sitemap arriba", file=sys.stderr)

    all_products = []
    for i, url in enumerate(product_urls[:MAX_PRODUCTS]):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                print(f"  aviso: {url} -> status {r.status_code}", file=sys.stderr)
                continue
            jsonld = extract_jsonld_product(r.text, url)
            if i == 0:
                print(f"DEBUG primer producto -> ¿JSON-LD encontrado? {jsonld is not None}", file=sys.stderr)
                if jsonld is None:
                    print(f"DEBUG primer producto -> primeros 1000 caracteres del HTML: {r.text[:1000]}", file=sys.stderr)
            if jsonld:
                all_products.append(parse_product(jsonld, url))
        except Exception as e:
            print(f"  aviso: fallo en {url}: {e}", file=sys.stderr)
        time.sleep(0.3)  # no saturar el servidor de Dia
        if i % 25 == 0:
            print(f"  progreso: {i}/{min(len(product_urls), MAX_PRODUCTS)}", file=sys.stderr)

    output = {
        "store": "Dia",
        "region": "España",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": len(all_products),
        "products": all_products,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Total: {len(all_products)} productos", file=sys.stderr)


if __name__ == "__main__":
    main()
