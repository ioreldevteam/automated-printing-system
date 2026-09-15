"""Product retrieval (Section 92). Like the serial API, products are managed
locally by default (Section 15's `products` table is the local catalog,
maintained by an Admin via Settings). RemoteProductApiClient exists for the
case where a real product master system is introduced later.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.api.client import RetryingHttpClient
from app.config.loader import ApiConfig
from app.database.repositories import ProductRepository


@dataclass
class ProductInfo:
    product_code: str
    product_name: str
    description: str = ""


class ProductApiClient(ABC):
    @abstractmethod
    def list_products(self) -> list[ProductInfo]: ...


class LocalProductApiClient(ProductApiClient):
    def __init__(self, session: Session):
        self.repo = ProductRepository(session)

    def list_products(self) -> list[ProductInfo]:
        return [
            ProductInfo(product_code=p.product_code, product_name=p.product_name, description=p.description or "")
            for p in self.repo.list_active()
        ]


class RemoteProductApiClient(ProductApiClient):
    def __init__(self, http_client: RetryingHttpClient):
        self.http_client = http_client

    def list_products(self) -> list[ProductInfo]:
        data = self.http_client.request("GET", "/products")
        return [
            ProductInfo(product_code=item["product_code"], product_name=item["product_name"],
                        description=item.get("description", ""))
            for item in data.get("products", [])
        ]


def build_product_api_client(api_config: ApiConfig, session: Session) -> ProductApiClient:
    if api_config.mode == "remote":
        http_client = RetryingHttpClient(
            base_url=api_config.base_url, timeout_seconds=api_config.timeout_seconds,
            retry_count=api_config.retry_count, backoff_base_seconds=api_config.backoff_base_seconds,
            backoff_max_seconds=api_config.backoff_max_seconds, token=api_config.token,
        )
        return RemoteProductApiClient(http_client)
    return LocalProductApiClient(session)
