"""Small standard-library platform layer. No CCL or provider dependencies."""
import contextlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


@contextlib.contextmanager
def file_lock(path, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'\0')
                stream.flush()
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (13, 36):
                        raise
                    if not blocking:
                        raise BlockingIOError('File is locked') from error
                    time.sleep(.02)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.flock(stream, flags)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def executable_argv(argv):
    argv = list(argv)
    first = Path(argv[0])
    if first.suffix.lower() == '.py':
        return [sys.executable, '-X', 'utf8'] + argv
    if os.name == 'nt':
        resolved = Path(shutil.which(argv[0]) or argv[0])
        if resolved.name.lower() in ('codex.cmd', 'codex.bat'):
            entry = resolved.parent / 'node_modules/@openai/codex/bin/codex.js'
            node = shutil.which('node')
            if entry.is_file() and node:
                return [node, str(entry)] + argv[1:]
        if resolved.name.lower() in ('claude.cmd', 'claude.bat'):
            package = resolved.parent / 'node_modules/@anthropic-ai/claude-code'
            native = package / 'bin/claude.exe'
            if native.is_file():
                return [str(native)] + argv[1:]
            entry, node = package / 'cli.js', shutil.which('node')
            if entry.is_file() and node:
                return [node, str(entry)] + argv[1:]
    return argv


def process_options():
    return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}


def terminate_tree(process):
    if os.name == 'nt':
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
