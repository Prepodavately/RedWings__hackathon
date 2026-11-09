"""
Пайплайн сборки финальных витрин data/processed/*.parquet.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)
"""

import pandas as pd


def build_processed_tables() -> None:
    """
    TODO (Dev 1): Соберите cities_features.parquet и routes_proof.parquet в data/processed/.
    """
    pass


def get_network_routes(hypothesis: str, hub_iata: str = "KUF") -> pd.DataFrame:
    """
    TODO (Dev 1): Верните DataFrame с 8-12 маршрутами и пруфами из data/processed/routes_proof.parquet.
    """
    pass


if __name__ == "__main__":
    build_processed_tables()
