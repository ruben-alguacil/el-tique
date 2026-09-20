"""
Descarga el catálogo de Alcampo recorriendo su árbol completo de categorías.

Alcampo no tiene API abierta, pero cada página renderiza un bloque
window.__INITIAL_STATE__ con todos los datos, incluido un mapa con las
350 categorías del catálogo (root.data.categories.categories) y, dentro de
cada página de categoría "hoja" (sin subcategorías), el detalle de sus
productos (root.data.products.productEntities).

Encontrado por ingeniería inversa manual, con la ayuda de Claude, en
septiembre de 2026. Si Alcampo cambia su web, esto puede romperse: pega el
error a Claude y lo revisamos igual que la primera vez.

Uso: python scrape_alcampo.py > prices_alcampo.json
"""
import json
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


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    if r.status_code != 200:
        print(f"  aviso: {url} -> status {r.status_code}", file=sys.stderr)
        return None
    return r.text


def extract_initial_state(html):
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    try:
        data, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return None
    return data


def safe_get(obj, *path):
    for p in path:
        if isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return None
    return obj


def get_leaf_categories():
    """Descarga el árbol completo de categorías y devuelve solo las 'hoja'
    (sin subcategorías), que son las que tienen productos directamente."""
    html = fetch(f"{BASE}/categories")
    if html is None:
        return []
    state = extract_initial_state(html)
    if state is None:
        print("DEBUG -> no se pudo extraer __INITIAL_STATE__ de la página de categorías", file=sys.stderr)
        return []

    tree = safe_get(state, "data", "categories", "categories")
    if not isinstance(tree, dict):
        print("DEBUG -> no se encontró data.categories.categories como diccionario", file=sys.stderr)
        return []

    leaves = []
    for cat_id, cat in tree.items():
        if not isinstance(cat, dict):
            continue
        children = cat.get("children") or []
        if len(children) == 0 and cat.get("fullURLPath"):
            leaves.append({
                "id": cat_id,
                "name": cat.get("name"),
                "path": cat.get("fullURLPath"),
            })
    print(f"DEBUG -> {len(tree)} categorías totales, {len(leaves)} son hoja (con productos)", file=sys.stderr)
    return leaves


def parse_product(entity, category_name):
    price = entity.get("price", {}) or {}
    current = price.get("current", {}) or {}
    unit = (price.get("unit") or {}).get("current", {}) or {}
    return {
        "id": entity.get("productId"),
        "name": entity.get("name"),
        "brand": entity.get("brand"),
        "category": category_name,
        "price": float(current["amount"]) if current.get("amount") else None,
        "currency": current.get("currency"),
        "reference_price": float(unit["amount"]) if unit.get("amount") else None,
        "available": entity.get("available"),
    }


def scrape_category(path, name):
    url = path if path.startswith("http") else f"{BASE}{path}"
    html = fetch(url)
    if html is None:
        return []
    state = extract_initial_state(html)
    if state is None:
        return []
    entities = safe_get(state, "data", "products", "productEntities")
    if not isinstance(entities, dict):
        return []
    return [parse_product(e, name) for e in entities.values()]


def main():
    leaves = get_leaf_categories()
    if not leaves:
        print("DEBUG -> sin categorías, abortando", file=sys.stderr)
        print(json.dumps({
            "store": "Alcampo", "region": "España",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "product_count": 0, "products": [],
        }, ensure_ascii=False, indent=2))
        return

    all_products = {}  # dedupe por id, porque un mismo producto puede salir en varias categorías
    for i, cat in enumerate(leaves):
        print(f"  [{i + 1}/{len(leaves)}] {cat['name']}", file=sys.stderr)
        try:
            products = scrape_category(cat["path"], cat["name"])
            for p in products:
                if p.get("id"):
                    all_products[p["id"]] = p
        except Exception as e:
            print(f"    aviso: fallo en '{cat['name']}': {e}", file=sys.stderr)
        time.sleep(0.4)  # no saturar el servidor de Alcampo

    output = {
        "store": "Alcampo",
        "region": "España",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "product_count": len(all_products),
        "products": list(all_products.values()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Total: {len(all_products)} productos únicos", file=sys.stderr)


if __name__ == "__main__":
    main()
