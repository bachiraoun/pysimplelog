# Simple Logger

This package is a simple yet complete logging management system for Python-based applications.

* Logging to multiple streams simultaneously: by default stdout (terminal) and a rotating log file.
* Any number of additional user-defined output sinks can be registered via `add_sink()`.
* Non-blocking enqueue mode routes all I/O to a background thread for latency-sensitive callers.
* Context-aware bound loggers returned by `bind()` prepend structured key-value pairs to every message.
* Exception capture via `catch()` works as both a decorator and a context manager.
* Caller tagging (`callerInfo=True`) prepends `[file:line in func]` to each log line automatically.
* Per-message count constraints, message size limits, and data size limits are supported.
* Logging text formatting (text colour, text weight, background colour) is allowed when the stream supports it.
* Adding as many logging levels and types as needed is possible.
* A singleton implementation (`SingleLogger`) is provided for application-wide shared loggers.

## Requirements

Python 3.6 or later.

## Installation

```
pip install pysimplelog
```

## Online Documentation

https://bachiraoun.github.io/pysimplelog/

To build and view the docs locally:

```
./build_docs.sh
```

This builds the Sphinx HTML docs (`docs/build/html/`) via the repo's
`.sphinx-venv` and opens `index.html` in your default browser -- one
command, nothing to activate by hand.

## SIEM / syslog forwarding (optional)

`pysimplelog.contrib` ships a zero-mandatory-dependency add-on that forwards
log records to a SIEM or syslog collector as RFC 5424 structured syslog over
TCP+TLS, UDP, or HTTP(S). It is pure `add_sink()` usage -- nothing in
`SimpleLog.py` is touched -- and its own background thread/queue keep a slow
or unreachable collector from ever blocking your application's normal
stdout/file logging.

```python
from pysimplelog import Logger
from pysimplelog.contrib import siem_sink, siem_transport

logger = Logger("my-app")

transport = siem_transport.TCPSyslogTransport("siem.example.com", 6514, useTls=True)
sink = siem_sink.attach(logger, transport,
                         logTypeFlags={"warn": True, "error": True, "critical": True},
                         defaultFlag=False)

logger.error("payment gateway timeout")

# at shutdown
siem_sink.detach(logger, sink)
```

See `contrib/siem_sink.py` and `contrib/siem_transport.py` for the full API
(UDP and HTTP/Splunk-HEC transports, retry/backoff tuning, circuit breaker,
drop/error callbacks) and `tests/test_siem_sink.py` for runnable examples.

## Author

Bachir Aoun
