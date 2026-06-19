"""Bronze Lakehouse Layer — Raw Ingestion & Partitioning."""

from __future__ import annotations

from pipeline.lake.bronze.writer import BronzePartitionWriter

__all__ = ["BronzePartitionWriter"]
