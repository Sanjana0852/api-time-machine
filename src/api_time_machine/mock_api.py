"""A mock shop API with two versions, for development and demos only.

Run it with:  python -m uvicorn api_time_machine.mock_api:app --port 8001

/v2 changes the response format in ways that break clients (price becomes a
string, seller.id is removed, ...), so replaying /v1 against /v2 shows what
API Time Machine detects. Product 101 matches examples/product_v1.json and
examples/product_v2.json exactly (a test keeps them in sync).
"""

from typing import Any

from fastapi import FastAPI, HTTPException

type Product = dict[str, Any]

PRODUCTS_V1: dict[int, Product] = {
    101: {
        "id": 101,
        "name": "Wireless Mouse",
        "price": 250,
        "currency": "INR",
        "stock": 12,
        "rating": 4.5,
        "discount": None,
        "seller": {"id": 7, "name": "Asha Electronics", "verified": True},
        "tags": ["electronics", "accessories"],
        "variants": [
            {"sku": "WM-BLK", "color": "black", "price": 250},
            {"sku": "WM-WHT", "color": "white", "price": 260},
        ],
    },
    102: {
        "id": 102,
        "name": "Mechanical Keyboard",
        "price": 3499,
        "currency": "INR",
        "stock": 5,
        "rating": 4.8,
        "discount": 15,
        "seller": {"id": 9, "name": "KeyCraft", "verified": True},
        "tags": ["electronics", "keyboards"],
        "variants": [{"sku": "MK-BLK", "color": "black", "price": 3499}],
    },
}

# v2 format changes, applied to every product: price is a string, seller.id is
# gone, delivery_days is new. Product 101 also has ordinary data changes.
PRODUCTS_V2: dict[int, Product] = {
    101: {
        "id": 101,
        "name": "Wireless Mouse",
        "price": "250",
        "currency": "INR",
        "stock": 9,
        "rating": 4,
        "discount": 10,
        "seller": {"name": "Asha Electronics", "verified": None},
        "tags": ["electronics", "accessories", "wireless"],
        "variants": [
            {"sku": "WM-BLK", "color": "black", "price": 250.5},
            {"sku": "WM-WHT", "color": "white", "price": 260},
        ],
        "delivery_days": 3,
    },
    102: {
        "id": 102,
        "name": "Mechanical Keyboard",
        "price": "3499",
        "currency": "INR",
        "stock": 5,
        "rating": 4.8,
        "discount": 15,
        "seller": {"name": "KeyCraft", "verified": True},
        "tags": ["electronics", "keyboards"],
        "variants": [{"sku": "MK-BLK", "color": "black", "price": 3499}],
        "delivery_days": 2,
    },
}

app = FastAPI(
    title="Mock Shop API",
    description="Demo API with two versions, used to try out API Time Machine. Development only.",
)


@app.get("/v1/products", tags=["v1"])
def list_products_v1() -> list[Product]:
    return list(PRODUCTS_V1.values())


@app.get("/v1/products/{product_id}", tags=["v1"])
def get_product_v1(product_id: int) -> Product:
    return _find_product(PRODUCTS_V1, product_id)


@app.get("/v2/products", tags=["v2"])
def list_products_v2() -> list[Product]:
    return list(PRODUCTS_V2.values())


@app.get("/v2/products/{product_id}", tags=["v2"])
def get_product_v2(product_id: int) -> Product:
    return _find_product(PRODUCTS_V2, product_id)


def _find_product(products: dict[int, Product], product_id: int) -> Product:
    if product_id not in products:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return products[product_id]
