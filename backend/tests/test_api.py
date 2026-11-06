import copy
import os
import unittest
from urllib.parse import urlparse


@unittest.skipUnless(
    os.environ.get("RUN_INTEGRATION") == "1",
    "Integration tests require a dedicated test database",
)
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database = urlparse(os.environ.get("DATABASE_URL", ""))

        if (
            database.path != "/planner_test"
            or database.hostname not in {"localhost", "127.0.0.1"}
        ):
            raise RuntimeError(
                "Integration tests may only use local planner_test database"
            )

        from fastapi.testclient import TestClient
        from app.main import app
        from app import db
        from app.config import OWNER

        cls.db = db
        cls.owner = OWNER
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.code = self.db.new_code(self.owner)

        response = self.client.post(
            "/api/auth/code",
            json={"code": self.code},
        )
        self.assertEqual(response.status_code, 200, response.text)

        self.headers = {
            "Authorization": f"Bearer {response.json()['token']}"
        }

    def get_document(self):
        response = self.client.get(
            "/api/state",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def planned_state(self):
        state = copy.deepcopy(self.db.DEFAULT_STATE)
        state["tasks"] = [
            {"id": "test-task", "title": "Test task", "order": 0}
        ]
        state["entries"] = {
            "test-task": {"2026-11-06": "planned"}
        }
        return state

    def test_health(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_state_requires_login(self):
        response = self.client.get("/api/state")

        self.assertEqual(response.status_code, 401)

    def test_login_code_is_single_use(self):
        response = self.client.post(
            "/api/auth/code",
            json={"code": self.code},
        )

        self.assertEqual(response.status_code, 401)

    def test_save_and_reject_stale_revision(self):
        original = self.get_document()
        state = self.planned_state()

        saved = self.client.put(
            "/api/state",
            headers=self.headers,
            json={
                "revision": original["revision"],
                "state": state,
            },
        )

        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(
            saved.json()["revision"],
            original["revision"] + 1,
        )

        stale = self.client.put(
            "/api/state",
            headers=self.headers,
            json={
                "revision": original["revision"],
                "state": self.db.DEFAULT_STATE,
            },
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.get_document()["state"], state)

    def test_invalid_state_does_not_change_data(self):
        original = self.get_document()
        invalid = self.planned_state()
        invalid["settings"] = {
            "wake": "23:00",
            "sleep": "07:00",
        }

        response = self.client.put(
            "/api/state",
            headers=self.headers,
            json={
                "revision": original["revision"],
                "state": invalid,
            },
        )

        self.assertEqual(response.status_code, 422)

        current = self.get_document()
        self.assertEqual(current["revision"], original["revision"])
        self.assertEqual(current["state"], original["state"])

    def test_bot_update_is_visible_through_api(self):
        original = self.get_document()

        saved = self.client.put(
            "/api/state",
            headers=self.headers,
            json={
                "revision": original["revision"],
                "state": self.planned_state(),
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        changed = self.db.mark_done(
            self.owner,
            "test-task",
            "2026-11-06",
        )
        self.assertTrue(changed)

        current = self.get_document()

        self.assertEqual(
            current["state"]["entries"]["test-task"]["2026-11-06"],
            "done",
        )
        self.assertEqual(
            current["revision"],
            saved.json()["revision"] + 1,
        )

    def test_logout_revokes_session(self):
        response = self.client.post(
            "/api/auth/logout",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            "/api/state",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 401)