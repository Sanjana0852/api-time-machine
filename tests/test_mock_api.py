"""Tests for the mock shop API used for development and demos."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_time_machine.diff import compare
from api_time_machine.mock_api import app
from api_time_machine.models import Severity

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_product_matches_example_file(client: TestClient, version: str) -> None:
    # Keeps the mock API and examples/ in sync, so replaying against the mock
    # API gives the same report as comparing the example files.
    expected = json.loads((EXAMPLES / f"product_{version}.json").read_text(encoding="utf-8"))

    response = client.get(f"/{version}/products/101")

    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_list_products(client: TestClient, version: str) -> None:
    response = client.get(f"/{version}/products")

    assert response.status_code == 200
    assert [product["id"] for product in response.json()] == [101, 102]


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_unknown_product_returns_404(client: TestClient, version: str) -> None:
    response = client.get(f"/{version}/products/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product 999 not found"}


def test_non_numeric_product_id_is_rejected(client: TestClient) -> None:
    # FastAPI validates the path parameter from the `int` type hint.
    assert client.get("/v1/products/abc").status_code == 422


@pytest.mark.parametrize("product_id", [101, 102])
def test_v2_has_breaking_changes_for_every_product(client: TestClient, product_id: int) -> None:
    # The point of the mock API: its versions differ in ways the engine must catch.
    old = client.get(f"/v1/products/{product_id}").json()
    new = client.get(f"/v2/products/{product_id}").json()

    assert any(change.severity is Severity.BREAKING for change in compare(old, new))
