"""Experience-Knowledge Tree: 2-layer management for WFXM.

Layer 1: Domain-based experience routing (8 domains)
Layer 2: Category-based organization (8 categories per domain)
"""

from butler.memory.experience.tree import ExperienceTree
from butler.memory.experience.taxonomy import DOMAINS, CATEGORIES
from butler.memory.experience.domain_router import DomainRouter

__all__ = [
    "ExperienceTree",
    "DomainRouter",
    "DOMAINS",
    "CATEGORIES",
]
