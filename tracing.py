"""Reads the identifiers of the active OpenTelemetry span, when the OpenTelemetry API is installed."""

try:
    from .record import TraceInfo
except ImportError:
    from record import TraceInfo

# The function that gives the active span. None until the API is found, and while it is missing
_getCurrentSpan = None


def trace_api_available():
    """
    Looks for the OpenTelemetry API.

    It is called when a sink asks for trace identifiers, never for each record. A missing API is looked for again at
    each call, so installing it and adding the sink again is enough.

    :Returns:
        #. isAvailable (bool): True when the API is installed and ready to be read.
    """
    global _getCurrentSpan
    if _getCurrentSpan is None:
        try:
            from opentelemetry import trace as otelTrace
            _getCurrentSpan = otelTrace.get_current_span
        except ImportError:
            return False
    return True


def read_current_trace():
    """
    Reads the identifiers of the active span.

    It never raises: logging must not fail because of tracing.

    :Returns:
        #. trace (TraceInfo, None): The identifiers of the active span, or None when there is no valid span, the API is
           missing, or reading it failed.
    """
    if _getCurrentSpan is None:
        return None
    try:
        spanContext = _getCurrentSpan().get_span_context()
        if not spanContext.is_valid:
            return None
        return TraceInfo(format(spanContext.trace_id, '032x'), format(spanContext.span_id, '016x'),
                         int(spanContext.trace_flags) & 0xFF)
    except Exception:
        return None
