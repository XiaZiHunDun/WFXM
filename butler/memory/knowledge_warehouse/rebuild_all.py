#!/usr/bin/env python3
"""Rebuild the knowledge warehouse from all sources.

Usage:
    python -m butler.memory.knowledge_warehouse.rebuild_all

This script:
1. Clears all existing data
2. Loads seed data
3. Loads extended seed data
4. Scans knowledge_import/ directory for user-provided files
5. Runs digestion pipeline to convert all materials to experiences
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from butler.memory.experience.tree import ExperienceTree
from butler.memory.knowledge_warehouse.digestion import DigestionPipeline
from butler.memory.knowledge_warehouse.ingestor import MaterialIngestor
from butler.memory.knowledge_warehouse.seed_data import load_seed_data
from butler.memory.knowledge_warehouse.seed_data_extended import load_extended_seed_data
from butler.memory.knowledge_warehouse.seed_data_massive import load_massive_seed_data
from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse


def clear_all_data() -> None:
    """Clear all knowledge warehouse data."""
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / ".wfxm_data"
    
    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"✓ Cleared existing data from {data_dir}")


def load_seed_materials(ingestor: MaterialIngestor) -> int:
    """Load all seed materials."""
    print("\nLoading seed materials...")
    load_seed_data(ingestor)
    
    print("Loading extended seed materials...")
    load_extended_seed_data(ingestor)
    
    print("Loading massive seed materials...")
    load_massive_seed_data(ingestor)
    
    stats = ingestor._warehouse.get_stats()
    print(f"✓ Seed materials loaded: {stats['total_materials']}")
    return stats["total_materials"]


def import_user_files(ingestor: MaterialIngestor) -> int:
    """Import user-provided files from knowledge_import/ directory.
    
    - user_uploads/: User-collected files (auto domain detection, source=user_collected)
    - ai_collected/: AI-collected files (domain from subdirectories, source=ai_collected)
    """
    project_root = Path(__file__).parent.parent.parent.parent
    import_dir = project_root / "knowledge_import"
    
    if not import_dir.exists():
        print(f"\n⚠️  knowledge_import/ directory not found at {import_dir}")
        return 0
    
    total_added = 0
    
    user_uploads_dir = import_dir / "user_uploads"
    if user_uploads_dir.exists():
        print(f"\nScanning user_uploads/ directory (auto domain detection)...")
        results = ingestor.batch_import_directory(
            str(user_uploads_dir),
            recursive=True,
            domain_hint="",
            source="user_collected",
        )
        added = sum(1 for _, was_added in results if was_added)
        skipped = len(results) - added
        print(f"✓ User files scanned: {len(results)} files, {added} added, {skipped} skipped")
        total_added += added
    else:
        print(f"\n⚠️  user_uploads/ directory not found")
    
    ai_collected_dir = import_dir / "ai_collected"
    if ai_collected_dir.exists():
        print(f"\nScanning ai_collected/ directory (domain from subdirectories)...")
        for domain_subdir in ai_collected_dir.iterdir():
            if domain_subdir.is_dir():
                domain_name = domain_subdir.name
                print(f"  - Processing {domain_name}/...")
                results = ingestor.batch_import_directory(
                    str(domain_subdir),
                    recursive=True,
                    domain_hint=domain_name,
                    source="ai_collected",
                )
                added = sum(1 for _, was_added in results if was_added)
                skipped = len(results) - added
                print(f"    ✓ {len(results)} files, {added} added, {skipped} skipped")
                total_added += added
    
    return total_added


def run_digestion() -> tuple[int, int]:
    """Run digestion pipeline to convert materials to experiences."""
    print("\nRunning digestion pipeline...")
    
    pipeline = DigestionPipeline()
    processed = pipeline.process_all()
    print(f"✓ Digestion completed: {processed} materials processed")
    
    stats = pipeline.get_stats()
    tree_stats = stats["experience_tree"]
    total_nodes = tree_stats["total_nodes"]
    
    print(f"\n=== Final Stats ===")
    print(f"Total materials: {stats['warehouse']['total_materials']}")
    print(f"Total experience nodes: {total_nodes}")
    print(f"\nDomain distribution:")
    for domain, info in sorted(tree_stats["domain_stats"].items(), key=lambda x: -x[1]["nodes"]):
        print(f"  {domain}: {info['nodes']} nodes")
    
    return processed, total_nodes


def main() -> int:
    print("=" * 60)
    print("WFXM Knowledge Warehouse Rebuild")
    print("=" * 60)
    
    try:
        clear_all_data()
        
        ingestor = MaterialIngestor()
        
        load_seed_materials(ingestor)
        import_user_files(ingestor)
        
        processed, total_nodes = run_digestion()
        
        print("\n" + "=" * 60)
        print(f"✓ Rebuild completed successfully!")
        print(f"  Materials: {ingestor._warehouse.get_stats()['total_materials']}")
        print(f"  Experience nodes: {total_nodes}")
        print("=" * 60)
        
        return 0
    
    except Exception as e:
        print(f"\n✗ Error during rebuild: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
