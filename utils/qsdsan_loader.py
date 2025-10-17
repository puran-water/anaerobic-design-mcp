#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Async lazy loader for QSDsan components.

This module provides non-blocking, thread-safe loading of QSDsan components
to prevent MCP event loop blocking during the 18-second import.

Key features:
- First call triggers async load in background thread
- All concurrent calls await the same load task
- Components are cached globally after first load
- Background warmup can be started after server startup
- Event loop remains responsive during 18s import
"""
import asyncio
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Global cache and synchronization
# Note: Only _load_task is used - no module-level Lock/Event to avoid cross-loop issues
_components_cache: Optional[object] = None
_load_task: Optional[asyncio.Task] = None


async def _do_load_qsdsan():
    """
    Perform the actual QSDsan import in a background thread.

    This function is executed via anyio.to_thread.run_sync to prevent blocking
    the event loop during the 18-second component creation.

    Uses AnyIO's managed thread pool (not asyncio's default executor) to avoid
    contention with FastMCP's internal tasks (middleware, stdio, logging).

    Returns:
        QSDsan Components object with ADM1+sulfur (30 components)
    """
    def _import_qsdsan():
        """Synchronous import work (runs in thread pool)."""
        logger.info("Starting QSDsan component creation in background thread...")
        import_start = time.time()

        # This is the expensive operation (18s)
        from utils.extract_qsdsan_sulfur_components import create_adm1_sulfur_cmps, set_global_components
        components = create_adm1_sulfur_cmps()

        # Set the global component set for backward compatibility
        set_global_components(components)

        import_elapsed = time.time() - import_start
        logger.info(f"QSDsan component creation completed in {import_elapsed:.1f}s")
        return components

    # Run synchronous import in AnyIO's thread pool (non-blocking for event loop)
    start_time = time.time()
    logger.info("Offloading QSDsan import to AnyIO thread pool...")

    import anyio
    components = await anyio.to_thread.run_sync(
        _import_qsdsan,
        limiter=anyio.to_thread.current_default_thread_limiter()
    )

    total_elapsed = time.time() - start_time
    logger.info(f"Total async load time: {total_elapsed:.1f}s (includes thread overhead)")

    return components


async def get_qsdsan_components():
    """
    Get QSDsan components, loading asynchronously if not yet cached.

    Thread-safe: Multiple concurrent calls will await the same load task.
    The first caller triggers the load, subsequent callers wait for completion.

    Returns:
        QSDsan Components object (ADM1_SULFUR_CMPS)

    Example:
        >>> components = await get_qsdsan_components()
        >>> # Use components for WasteStream creation
    """
    global _components_cache, _load_task

    # Fast path: already loaded
    if _components_cache is not None:
        logger.debug("QSDsan components retrieved from cache")
        return _components_cache

    # Slow path: need to load
    # First caller creates the load task on the RUNNING loop (no cross-loop contamination)
    if _load_task is None:
        logger.info("First caller - creating QSDsan load task on current event loop")
        _load_task = asyncio.create_task(_do_load_qsdsan())
    else:
        logger.info("Waiting for ongoing QSDsan load task...")

    # All callers (first and concurrent) await the same task
    _components_cache = await _load_task

    logger.info("QSDsan components now cached and ready")
    return _components_cache


def start_background_warmup():
    """
    Start loading QSDsan components in the background.

    Call this after MCP server startup to pre-warm the cache.
    The load happens asynchronously, so the server remains responsive.

    If a client calls a validation tool before warmup completes,
    they will await the same load task (no duplicate work).

    Example:
        >>> # In server.py main():
        >>> from utils.qsdsan_loader import start_background_warmup
        >>> asyncio.get_event_loop().call_soon(start_background_warmup)
        >>> mcp.run()
    """
    logger.info("Starting background QSDsan warmup task...")

    async def _warmup():
        try:
            await get_qsdsan_components()
            logger.info("Background QSDsan warmup completed successfully")
        except Exception as e:
            logger.error(f"Background QSDsan warmup failed: {e}", exc_info=True)

    # Schedule warmup task (don't block)
    asyncio.create_task(_warmup())


def is_loaded() -> bool:
    """
    Check if QSDsan components are already loaded.

    Returns:
        True if components are cached, False otherwise
    """
    return _components_cache is not None


async def wait_for_load(timeout: float = 30.0) -> bool:
    """
    Wait for QSDsan components to load (if loading is in progress).

    Args:
        timeout: Maximum seconds to wait (default 30s)

    Returns:
        True if loaded within timeout, False if timeout occurred
    """
    if _components_cache is not None:
        return True

    if _load_task is None:
        # Not even started loading yet
        return False

    try:
        await asyncio.wait_for(_load_task, timeout=timeout)
        return _components_cache is not None
    except asyncio.TimeoutError:
        logger.warning(f"QSDsan load did not complete within {timeout}s")
        return False
