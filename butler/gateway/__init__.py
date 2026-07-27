"""Butler-native WeChat gateway (``butler gateway``)."""

# Shim for backward compatibility: durable_outbox was moved to resilience module
try:
    from butler.resilience import durable_outbox
except ImportError:
    durable_outbox = None
