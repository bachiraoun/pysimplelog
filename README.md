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

## Author

Bachir Aoun
