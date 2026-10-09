# Simple Logger

This package is a simple yet complete logging management system for Python-based applications.

## Quick start

```python
from pysimplelog import logger

logger.info("Application started")
logger.warning("Disk almost full")
logger.info("User {} logged in", "ann")
logger.info("Order created", order_id=123, amount=12.5)
logger.add("logs/app.log", rotation="500 MB", retention="30 days")    ## a rotating log file, in one call
```

```
2026-10-08 18:45:02.761 | INFO     | pysimplelog | Application started
2026-10-08 18:45:02.761 | WARNING  | pysimplelog | Disk almost full
2026-10-08 18:45:02.762 | INFO     | pysimplelog | User ann logged in
2026-10-08 18:45:02.762 | INFO     | pysimplelog | Order created order_id=123 amount=12.5
```

There is nothing to set up: `logger` is made the first time it is used, and the console is coloured when it is a terminal.
The [user guide](https://bachiraoun.github.io/pysimplelog/guide/index.html) follows what you do with a logger, from the first
line to a production setup, and every example in it was run.

## Features

* A shared `logger` that works with no setup, and a `Logger` class for libraries and for anything that needs its own settings.
* `{}` formatting, `logger.info("User {} logged in", user)`, with values also kept as separate fields. `logger.opt(lazy=True)` builds a message only when a sink wants it, and `opt(depth=...)` keeps the real caller when you wrap the logger.
* `logger.add(target, ...)` adds a file (with `rotation`, `retention` and `compression`), a stream or a function in one call, with a `level`, a `format` and a `filter`.
* `PYSIMPLELOG_LEVEL`, `PYSIMPLELOG_FORMAT` and `PYSIMPLELOG_COLOR` set up the console without editing code, and `pysimplelog.disable("library")` silences a library, in every process with `PYSIMPLELOG_NAMESPACE_DISABLE`.
* Exceptions: `logger.exception(...)`, a shorter traceback for the console, and an opt-in `diagnose` that shows the values of the variables and hides secrets by name.
* Secrets: `redact_fields`, `redact_patterns` (URLs with passwords, bearer tokens, JWTs, `password=...`), `Secret(value)` and `hash_secrets()`. Control characters in fields are escaped so a value cannot forge a log line.
* Delivery you can reason about: explicit queue policies, counters for everything dropped, `flush()` that says whether it finished, and a report of what was lost at exit.

* Logging to multiple streams simultaneously: by default stdout (terminal) and a rotating log file.
* Any number of additional user-defined output sinks can be registered via `add_sink()`.
* Non-blocking enqueue mode routes all I/O to a background thread for latency-sensitive callers. A sink can have its own queue and thread. What a full queue does is explicit (`block`, `drop_newest`, `drop_oldest` or `reject`), and `sink_stats()` counts what every sink queued, delivered, failed and dropped.
* Context-aware bound loggers returned by `bind()`, and `with logger.context(request_id=...)` blocks, attach key-value pairs to the `context` of every record. The values follow the flow of the program through `contextvars`, also across asynchronous tasks.
* Exception capture via `catch()` works as both a decorator and a context manager.
* Caller tagging (`callerInfo=True`) prepends `[file:line in func]` to each log line automatically.
* Every log call builds one immutable structured `LogRecord`. Each sink renders it with its own formatter: readable text, JSON lines, a `{field}` template or any function.
* Processors (`add_processor()`) rewrite every record before any sink sees it. `redact_fields()` hides the value of sensitive keys such as passwords and tokens, and `redact_text()` turns a text function into a processor, e.g. to hide filesystem paths.
* Filters (`add_filter()`) drop whole records, and `set_sink_filter()` chooses by any field which records one sink receives.
* Python's standard `logging` flows in: `redirect_standard_logging(logger)` sends the records of the libraries an application uses through the same processors, filters and sinks, with `extra=` becoming fields and `logging.exception` keeping its traceback.
* An opt-in policy (`unknownLogTypePolicy='fallback'`) logs a misspelled log type under a fallback type instead of raising.
* Per-message count constraints, message size limits, and data size limits are supported.
* Logging text formatting (text colour, text weight, background colour) is allowed when the stream supports it.
* Adding as many logging levels and types as needed is possible.
* A singleton implementation (`SingleLogger`) is provided for application-wide shared loggers.

## Requirements

Python 3.10 or later.

## Installation

Get the package from GitHub, into a folder named `pysimplelog`:

```
git clone https://github.com/bachiraoun/pysimplelog.git
```

Then put that folder where Python can import it: in your `site-packages` folder, or in any folder that is on `PYTHONPATH`.

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
TCP+TLS, UDP, or HTTP(S). It is plain `add_sink()` usage, and its own
background thread/queue keep a slow
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

Records carry named fields, passed as keyword arguments: `logger.info("Order created", order_id=123)`.
The text layout writes them as `key=value` after the message, JSON keeps them as they are, and the SIEM sink
writes them as a second structured-data element of the RFC 5424 line. `exc_info=True` (or an exception
object) records the exception being handled, with its type, message and traceback.

### Delivery

Records wait in an in-memory queue, so some are lost when the collector stays down longer than the retries and the circuit
breaker cover, when the queue is full (the oldest record is dropped), or when the application stops while records are still queued.
Losses are counted in `sink.stats` and reported through `onDrop` / `onError`. To keep records through an outage or a crash, give the
sink a disk spool: see *Durable delivery* below.

## Enrichment and filters

`add_context(service=..., environment=..., host=...)` is a processor that puts the same values in every record, and `match_logger`, `match_module` and `match_field` are filters that choose by the structure of a record, for example to silence a noisy library or send two categories to one sink. The JSON layout is documented in full, a test keeps the page and the formatter equal, and `JsonFormatter(utc=True)` writes UTC timestamps.

## Messages that must appear

`logger.force_log("info", "Shutting down")` writes a record whatever the levels, the log types, the filters and `disable()` say. It goes to every output that is switched on, or only to the ones named in `sinks=[...]`; the processors still run, so redaction applies, and `opt()` and `bind()` work with it. See *Multiple sinks* in the guide.

## Log files

A `FileSink` rotates by size, keeps a number of files (`roll`) and deletes rotated files older than `maxAge`, and can compress rotated files to `.gz` (`compress='gz'`), in a thread of its own. There is no monitor thread: the age is tested when something happens, and `logger.maintain()` does the housekeeping of every sink on demand, for a scheduler. See *Log files* in the documentation.

## Durable delivery

`spool=` on a sink keeps its records on disk until the sink has delivered them: a collector that is down, or a crash, loses nothing that was written. Delivery is in order, retried, and at-least-once, with a stable `event_id` on every record so a receiver can recognise a repeat. A process that died leaves its files for another to send. See *Durable delivery* in the documentation and `examples/10_durable_delivery.py`.

## OpenTelemetry logs (optional)

`pysimplelog.contrib.otlp_sink.attach(logger, "https://collector.example.org:4318", resource={"service.name": "orders"})` sends records to an OpenTelemetry Collector, or any backend that takes OTLP over HTTP, in groups of up to 512, with the standard library only. A record keeps its trace and span identifiers when `opentelemetry-api` is installed, a `spool=` keeps the records through an outage or a crash, and a payload the receiver refuses is cut in halves until the one record at fault is found and parked. It was compared with the official OpenTelemetry encoder and checked against the OpenTelemetry Collector 0.162.0. See *OpenTelemetry logs (OTLP)* in the documentation, `examples/11_opentelemetry_logs.py` and `examples/12_real_collector_check.py`.

## Benchmark

`python3 pysimplelog/benchmarks/bench_logging.py` measures the cost of one log call for pysimplelog, the standard `logging` module, and Loguru and structlog when they are installed. The numbers belong to the machine they are measured on.

## API stability

From 6.0 the names in `pysimplelog.__all__`, the public methods and properties of `Logger`, and the
arguments of `Logger()` and `add_sink()` are stable. Later 6.x releases only add to them. A removal
or a change of meaning waits for 7.0.

## Author

Bachir Aoun
