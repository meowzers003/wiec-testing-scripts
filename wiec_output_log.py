import contextlib
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


OUTPUT_LOG_DIR = Path.cwd() / "wiec output logs"
_log_file: Optional[TextIO] = None
_original_stdout: Optional[TextIO] = None
_original_stderr: Optional[TextIO] = None


def safe_filename_part(value: str) -> str:
    value = value.strip() or "wiec_qc_test"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "wiec_qc_test"


class Tee:
    def __init__(self, terminal_stream: TextIO, log_stream: TextIO):
        self.terminal_stream = terminal_stream
        self.log_stream = log_stream

    def write(self, data: str) -> int:
        self.terminal_stream.write(data)
        self.terminal_stream.flush()
        self.log_stream.write(data)
        self.log_stream.flush()
        return len(data)

    def flush(self) -> None:
        self.terminal_stream.flush()
        self.log_stream.flush()

    def isatty(self) -> bool:
        return self.terminal_stream.isatty()


class LogOnly:
    def __init__(self, log_stream: TextIO):
        self.log_stream = log_stream

    def write(self, data: str) -> int:
        self.log_stream.write(data)
        self.log_stream.flush()
        return len(data)

    def flush(self) -> None:
        self.log_stream.flush()


def start_output_log(test_name: str) -> Path:
    global _log_file, _original_stdout, _original_stderr

    OUTPUT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filename = f"{safe_filename_part(test_name)}_{timestamp}_wiec_qc_outputlog.txt"
    log_path = OUTPUT_LOG_DIR / filename

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    _log_file = log_path.open("w")
    sys.stdout = Tee(_original_stdout, _log_file)
    sys.stderr = Tee(_original_stderr, _log_file)
    print(f"WIEC output log: {log_path}")
    return log_path


def stop_output_log() -> None:
    global _log_file

    if _log_file is None:
        return

    if _original_stdout is not None:
        sys.stdout = _original_stdout
    if _original_stderr is not None:
        sys.stderr = _original_stderr

    _log_file.close()
    _log_file = None


def is_active() -> bool:
    return _log_file is not None


def log(message: str = "") -> None:
    if _log_file is None:
        return
    _log_file.write(f"{message}\n")
    _log_file.flush()


@contextlib.contextmanager
def terminal_suppressed():
    if _log_file is None:
        yield
        return

    with contextlib.redirect_stdout(LogOnly(_log_file)):
        yield


def countdown_sleep(seconds: int, message: str) -> None:
    log(f"{message}: waiting {seconds} seconds")
    for remaining in range(int(seconds), 0, -1):
        print(f"\r{message}: {remaining}s remaining", end="", flush=True)
        time.sleep(1)
    print(f"\r{message}: done{' ' * 20}")
    log(f"{message}: wait complete")
