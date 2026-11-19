import ast
import contextlib
import io
import multiprocessing
import secrets
import threading
import time
import traceback


MAX_SESSIONS = 10
SESSION_IDLE_SECONDS = 1800
EXECUTION_TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 65536


class LimitedOutput(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.remaining = MAX_OUTPUT_CHARS
        self.truncated = False

    def write(self, text):
        if self.remaining:
            self.parts.append(text[:self.remaining])
        if len(text) > self.remaining:
            self.truncated = True
        self.remaining -= min(len(text), self.remaining)
        return len(text)

    def value(self):
        output = "".join(self.parts)
        return output + ("\n[output truncated]" if self.truncated else "")


def _interpreter(connection):
    namespace = {"__name__": "__console__"}
    while True:
        try:
            source = connection.recv()
        except EOFError:
            break
        output = LimitedOutput()
        success = True
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                tree = ast.parse(source, mode="exec")
                expression = None
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    expression = ast.Expression(tree.body.pop().value)
                    ast.fix_missing_locations(expression)
                exec(compile(tree, "<console>", "exec"), namespace)
                if expression is not None:
                    result = eval(compile(expression, "<console>", "eval"), namespace)
                    if result is not None:
                        print(repr(result))
        except BaseException:
            success = False
            traceback.print_exc(file=output)
        try:
            connection.send({"ok": success, "output": output.value()})
        except (BrokenPipeError, EOFError, OSError):
            break
    connection.close()


class Session:
    def __init__(self):
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_interpreter, args=(child,))
        try:
            self.process.start()
        except BaseException:
            self.connection.close()
            child.close()
            raise
        child.close()
        self.lock = threading.Lock()
        self.last_used = time.monotonic()

    def close(self):
        self.connection.close()
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()

    def create(self):
        with self.lock:
            now = time.monotonic()
            for session_id, session in list(self.sessions.items()):
                if now - session.last_used > SESSION_IDLE_SECONDS and session.lock.acquire(False):
                    try:
                        self.sessions.pop(session_id)
                        session.close()
                    finally:
                        session.lock.release()
            if len(self.sessions) >= MAX_SESSIONS:
                return None
            session_id = secrets.token_urlsafe(24)
            self.sessions[session_id] = Session()
            return session_id

    def _acquire(self, session_id):
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                return None, "not_found"
            if not session.lock.acquire(False):
                return None, "busy"
            if time.monotonic() - session.last_used > SESSION_IDLE_SECONDS:
                self.sessions.pop(session_id)
                session.close()
                session.lock.release()
                return None, "not_found"
            return session, None

    def execute(self, session_id, source):
        session, error = self._acquire(session_id)
        if error:
            return None, error
        try:
            session.last_used = time.monotonic()
            try:
                session.connection.send(source)
                if not session.connection.poll(EXECUTION_TIMEOUT_SECONDS):
                    error = "timeout"
                else:
                    result = session.connection.recv()
                    session.last_used = time.monotonic()
                    return result, None
            except (BrokenPipeError, EOFError, OSError):
                error = "terminated"
            with self.lock:
                self.sessions.pop(session_id, None)
            session.close()
            return None, error
        finally:
            session.lock.release()

    def delete(self, session_id):
        session, error = self._acquire(session_id)
        if error:
            return error
        try:
            with self.lock:
                self.sessions.pop(session_id, None)
            session.close()
            return None
        finally:
            session.lock.release()

    def close_all(self):
        with self.lock:
            for session in self.sessions.values():
                session.close()
            self.sessions.clear()
