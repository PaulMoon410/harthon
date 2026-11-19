import os
import unittest
from unittest.mock import patch

import app
import python_sessions


KEY = "test-key-" + "x" * 32
HEADERS = {"Authorization": "Bearer " + KEY}


class ConsoleApiTests(unittest.TestCase):
    def setUp(self):
        self.key = patch.dict(os.environ, {"PYTHON_API_KEY": KEY})
        self.key.start()
        self.client = app.app.test_client()

    def tearDown(self):
        app.sessions.close_all()
        self.key.stop()

    def create_session(self):
        response = self.client.post("/api/sessions", headers=HEADERS)
        self.assertEqual(response.status_code, 201)
        return response.json["session_id"]

    def execute(self, session_id, code):
        return self.client.post(
            f"/api/sessions/{session_id}/execute",
            headers=HEADERS,
            json={"code": code},
        )

    def test_authentication_fails_closed(self):
        self.assertEqual(self.client.post("/api/sessions").status_code, 401)
        with patch.dict(os.environ, {"PYTHON_API_KEY": ""}):
            self.assertEqual(self.client.post("/api/sessions", headers=HEADERS).status_code, 503)
        self.assertEqual(self.client.get("/console").status_code, 200)
        self.assertEqual(self.client.get("/").location, "/console")

    def test_state_output_errors_and_deletion(self):
        session_id = self.create_session()
        self.assertEqual(self.execute(session_id, "x = 42\nprint('hello')").json,
                         {"ok": True, "output": "hello\n"})
        self.assertEqual(self.execute(session_id, "x + 1").json,
                         {"ok": True, "output": "43\n"})
        result = self.execute(session_id, "1 / 0")
        self.assertFalse(result.json["ok"])
        self.assertIn("ZeroDivisionError", result.json["output"])
        self.assertEqual(self.execute(session_id, "x").json["output"], "42\n")
        self.assertEqual(self.client.delete(f"/api/sessions/{session_id}", headers=HEADERS).status_code, 204)
        self.assertEqual(self.execute(session_id, "x").status_code, 404)

    def test_sessions_are_separate_and_invalid_input_rejected(self):
        first = self.create_session()
        second = self.create_session()
        self.execute(first, "value = 123")
        self.assertIn("NameError", self.execute(second, "value").json["output"])
        response = self.client.post(f"/api/sessions/{first}/execute", headers=HEADERS, json={"code": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(f"/api/sessions/{first}/execute", json={"code": "1"}).status_code, 401)

    def test_timeout_removes_session(self):
        session_id = self.create_session()
        self.assertTrue(self.execute(session_id, "1").json["ok"])
        with patch.object(python_sessions, "EXECUTION_TIMEOUT_SECONDS", 0.2):
            response = self.execute(session_id, "while True: pass")
        self.assertEqual(response.status_code, 504)
        self.assertEqual(self.execute(session_id, "1").status_code, 404)

    def test_busy_and_idle_sessions(self):
        session_id = self.create_session()
        session = app.sessions.sessions[session_id]
        with session.lock:
            self.assertEqual(self.execute(session_id, "1").status_code, 409)
            self.assertEqual(self.client.delete(f"/api/sessions/{session_id}", headers=HEADERS).status_code, 409)
        session.last_used -= python_sessions.SESSION_IDLE_SECONDS + 1
        self.assertEqual(self.execute(session_id, "1").status_code, 404)


if __name__ == "__main__":
    unittest.main()
