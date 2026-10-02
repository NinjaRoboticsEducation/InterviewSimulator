"""Bounded cancellation for native speech tools and the model-server launcher."""

from __future__ import annotations

import signal
import subprocess
import threading
import time
from contextvars import ContextVar

native_cancel: ContextVar[threading.Event | None] = ContextVar("native_cancel", default=None)


def terminate(process: subprocess.Popen) -> None:
    """Terminate only this owned child process, then reap it within two seconds."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run(args, *, timeout=None, check=False, capture_output=False, input=None, **kwargs):
    cancelled = native_cancel.get()
    if cancelled is None:
        return subprocess.run(
            args, timeout=timeout, check=check, capture_output=capture_output, input=input, **kwargs
        )
    if cancelled.is_set():
        raise InterruptedError("Native operation cancelled")
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    began = time.monotonic()
    with subprocess.Popen(args, **kwargs) as process:
        pending_input = input
        while True:
            try:
                if cancelled.is_set():
                    raise InterruptedError("Native operation cancelled")
                if timeout is not None and time.monotonic() - began >= timeout:
                    raise subprocess.TimeoutExpired(args, timeout)
                stdout, stderr = process.communicate(input=pending_input, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if timeout is not None and time.monotonic() - began >= timeout:
                    terminate(process)
                    raise
                pending_input = None
            except BaseException:
                terminate(process)
                raise
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def serve_native(args) -> None:
    """Forward Ctrl+C/termination to the child even when only the wrapper is signalled."""
    process = subprocess.Popen(args)
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        code = process.wait()
        if code and code not in {-signal.SIGINT, -signal.SIGTERM}:
            raise subprocess.CalledProcessError(code, args)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            terminate(process)
        finally:
            signal.signal(signal.SIGTERM, previous)
