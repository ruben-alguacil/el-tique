"""
Descarga el catálogo completo de Mercadona para Madrid capital.

Usa la API interna (no oficial) de tienda.mercadona.es. Mercadona no publica
esta API para terceros: puede cambiar sin avisar. Si un día deja de funcionar,
pega el error a Claude y lo arreglamos.

Uso: python scrape_mercadona.py > prices_mercadona.json
"""
import json
import sys
import time
import requests

BASE = "https://tienda.mercadona.es/api"
WAREHOUSE = "mad1"  # código de la zona de reparto de Madrid capital
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ElTiquePriceBot/1.0)"}


def get_categories():
    url = f"{BASE}/categories/"
    r = requests.get(url, headers=HEADERS, params={"lang": "es", "wh": WAREHOUSE}, timeout=20)
    print(f"DEBUG categories -> status {r.status_code}, url final: {r.url}", file=sys.stderr)
    r.raise_for_status()
    data = r.json()
    print(f"DEBUG categories -> claves de nivel superior: {list(data.keys())}", file=sys.stderr)
    results = data.get("results", [])
    if not results:
        print(f"DEBUG categories -> respuesta completa (primeros 1000 caracteres): {json.dumps(data, ensure_ascii=False)[:1000]}", file=sys.stderr)
    return results


def get_category_products(cat_id, debug=False):
    url = f"{BASE}/categories/{cat_id}/"
    r = requests.get(url, headers=HEADERS, params={"lang": "es", "wh": WAREHOUSE}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if debug:
        print(f"DEBUG categoría {cat_id} -> claves de nivel superior: {list(data.keys())}", file=sys.stderr)
        print(f"DEBUG categoría {cat_id} -> respuesta completa (primeros 1500 caracteres): {json.dumps(data, ensure_ascii=False)[:1500]}", file=sys.stderr)
    products = []
    for sub in data.get("categories", []):
        products.extend(sub.get("products", []))
    return products


def parse_product(raw, category_name):
    pi = raw.get("price_instructions", {}) or {}
    try:
        price = float(pi.get("bulk_price") or 0)
    except (TypeError, ValueError):
        price = None
    return {
        "id": raw.get("id"),
        "name": raw.get("display_name"),
        "packaging": raw.get("packaging"),
        "category": category_name,
        "price": price,
        "reference_price": pi.get("unit_price"),
        "reference_unit": pi.get("size_format"),
        "url": raw.get("share_url"),
    }


def main():
    all_products = []
    categories = get_categories()
    print(f"Encontradas {len(categories)} categorías de nivel superior", file=sys.stderr)

    for i, cat in enumerate(categories):
        cat_id = cat.get("id")
        cat_name = cat.get("name", "")
        print(f"  Descargando: {cat_name}", file=sys.stderr)
        try:
            products = get_category_products(cat_id, debug=(i == 0))
            print(f"    -> {len(products)} productos encontrados en '{cat_name}'", file=sys.stderr)
        except Exception as e:
            print(f"    aviso: no se pudo leer '{cat_name}': {e}", file=sys.stderr)
            continue
        for p in products:
            all_products.append(parse_product(p, cat_name))
        time.sleep(0.4)  # no saturar el servidor de Mercadona

    output = {
        "store": "Mercadona",
        "region": "Madrid capital",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": len(all_products),
        "products": all_products,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Total: {len(all_products)} productos", file=sys.stderr)


if __name__ == "__main__":
    main()
