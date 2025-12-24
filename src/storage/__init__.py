"""
Módulo de storage: persistência de dados coletados.
Suporta SQLite, CSV e Parquet.
"""

from src.storage.base import BaseStorage, StorageType
from src.storage.sqlite_storage import SQLiteStorage
from src.storage.file_storage import CSVStorage, ParquetStorage
from src.storage.manager import StorageManager

__all__ = [
    "BaseStorage",
    "StorageType",
    "SQLiteStorage",
    "CSVStorage",
    "ParquetStorage",
    "StorageManager",
]