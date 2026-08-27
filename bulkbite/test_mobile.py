from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import frappe
import jwt
from frappe.tests import IntegrationTestCase

from bulkbite.mobile import (
	MOBILE_AUTH_SCHEME,
	MOBILE_JWT_ALGORITHM,
	MOBILE_JWT_AUDIENCE,
	MOBILE_JWT_ISSUER,
	_issue_access_token,
	_token_hash,
	validate_mobile_jwt,
)


class TestBulkBiteMobileAuth(IntegrationTestCase):
	def test_access_token_contains_private_mobile_contract(self):
		secret = "test-mobile-secret"
		with patch("bulkbite.mobile._get_mobile_jwt_secret", return_value=secret):
			token = _issue_access_token("Administrator")
		claims = jwt.decode(
			token,
			secret,
			algorithms=[MOBILE_JWT_ALGORITHM],
			audience=MOBILE_JWT_AUDIENCE,
			issuer=MOBILE_JWT_ISSUER,
		)
		self.assertEqual(claims["sub"], "Administrator")
		self.assertEqual(claims["typ"], "access")

	def test_refresh_tokens_are_only_stored_as_hashes(self):
		self.assertEqual(len(_token_hash("private-refresh-token")), 64)
		self.assertNotIn("private-refresh-token", _token_hash("private-refresh-token"))

	def test_auth_hook_sets_enabled_user_and_preserves_form_values(self):
		secret = "test-mobile-secret"
		now = datetime.now(UTC)
		token = jwt.encode(
			{
				"sub": "Administrator",
				"iss": MOBILE_JWT_ISSUER,
				"aud": MOBILE_JWT_AUDIENCE,
				"typ": "access",
				"jti": "test-jti",
				"iat": now,
				"exp": now + timedelta(minutes=5),
			},
			secret,
			algorithm=MOBILE_JWT_ALGORITHM,
		)
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict({"payload": "kept"})
		with (
			patch("bulkbite.mobile._get_mobile_jwt_secret", return_value=secret),
			patch("bulkbite.mobile.frappe.get_request_header", return_value=f"{MOBILE_AUTH_SCHEME} {token}"),
			patch("bulkbite.mobile.frappe.db.get_value", return_value=1),
		):
			validate_mobile_jwt()
		self.assertEqual(frappe.session.user, "Administrator")
		self.assertEqual(frappe.local.form_dict.payload, "kept")

	def test_auth_hook_ignores_standard_bearer_tokens(self):
		frappe.set_user("Guest")
		with patch("bulkbite.mobile.frappe.get_request_header", return_value="Bearer standard-token"):
			validate_mobile_jwt()
		self.assertEqual(frappe.session.user, "Guest")
