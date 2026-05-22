"""M4: facade module and legacy memory_plugin re-export."""

from __future__ import annotations


def test_memory_plugin_reexports_facade():
    from butler.memory import facade
    from butler.memory_plugin import ButlerMemoryProvider, ButlerMemoryService

    assert ButlerMemoryService is facade.ButlerMemoryService
    assert ButlerMemoryProvider is facade.ButlerMemoryProvider


def test_memory_package_lazy_exports():
    from butler.memory import ButlerMemoryService as pkg_svc
    from butler.memory.facade import ButlerMemoryService as facade_svc

    assert pkg_svc is facade_svc
