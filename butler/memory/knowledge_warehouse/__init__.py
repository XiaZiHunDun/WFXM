"""Knowledge Warehouse — material storage and digestion pipeline.

Materials flow:
    Ingest → raw → queue → digest (LLM extract) → write to ExperienceTree → digested

Supported source types:
    - text: direct text content
    - url: web page URL
    - file: local file path (PDF, Markdown, etc.)
"""

from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse
from butler.memory.knowledge_warehouse.ingestor import MaterialIngestor
from butler.memory.knowledge_warehouse.digestion import DigestionPipeline

__all__ = [
    "KnowledgeWarehouse",
    "MaterialIngestor",
    "DigestionPipeline",
]
