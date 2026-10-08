"""Contrato HTTP del login sin depender de una base PostgreSQL externa."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.rate_limit import _hits
from app.core.security import TokenType, decode_token, hash_password
from app.main import app


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.user = SimpleNamespace(
            id=uuid4(),
            email="familia@example.com",
            password_hash=hash_password("Correcta123!"),
        )

    def setUp(self) -> None:
        _hits.clear()
        self.db = SimpleNamespace(scalar=AsyncMock(return_value=self.user))

        async def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        _hits.clear()

    def test_login_issues_tokens_for_registered_user(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.user.email, "password": "Correcta123!"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], str(self.user.id))
        self.assertEqual(body["email"], self.user.email)
        self.assertIsNone(body["role"])
        self.assertEqual(decode_token(body["access_token"], TokenType.ACCESS), self.user.id)
        self.assertEqual(decode_token(body["refresh_token"], TokenType.REFRESH), self.user.id)

    def test_wrong_password_and_unknown_email_share_generic_error(self) -> None:
        wrong_password = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.user.email, "password": "Incorrecta123!"},
        )
        self.db.scalar.return_value = None
        unknown_email = self.client.post(
            "/api/v1/auth/login",
            json={"email": "nadie@example.com", "password": "Incorrecta123!"},
        )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        for response in (wrong_password, unknown_email):
            error = response.json()["error"]
            self.assertEqual(error["code"], "INVALID_CREDENTIALS")
            self.assertEqual(error["message"], "Correo o contraseña incorrectos.")
            self.assertIn("request_id", error)

    def test_invalid_body_uses_standard_validation_error(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": "invalido", "password": ""},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_login_is_rate_limited_after_five_attempts(self) -> None:
        for _ in range(5):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"email": self.user.email, "password": "Incorrecta123!"},
            )
            self.assertEqual(response.status_code, 401)

        blocked = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.user.email, "password": "Incorrecta123!"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"]["code"], "RATE_LIMITED")


if __name__ == "__main__":
    unittest.main()
