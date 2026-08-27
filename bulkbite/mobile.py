from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import frappe
import jwt
from frappe import _
from frappe.auth import validate_ip_address
from frappe.installer import update_site_config
from frappe.twofactor import should_run_2fa
from frappe.utils import add_days, get_datetime, now_datetime


# =============================================================================
# region MOBILE AUTH CONFIGURATION
# =============================================================================

MOBILE_JWT_SECRET_KEY = "bulkbite_mobile_jwt_secret"
MOBILE_JWT_ALGORITHM = "HS256"
MOBILE_JWT_ISSUER = "bulkbite"
MOBILE_JWT_AUDIENCE = "bulkbite-admin-mobile"
MOBILE_AUTH_SCHEME = "BulkBite"
MOBILE_ACCESS_TOKEN_MINUTES = 15
MOBILE_REFRESH_TOKEN_DAYS = 30
MOBILE_ROLES = {"BulkBite Worker", "BulkBite Manager", "BulkBite Accountant"}


def setup_mobile_jwt_secret():
	"""Create one private native-token signing secret for this Frappe site."""
	if not frappe.conf.get(MOBILE_JWT_SECRET_KEY):
		update_site_config(MOBILE_JWT_SECRET_KEY, secrets.token_urlsafe(64))


def _get_mobile_jwt_secret():
	secret = frappe.conf.get(MOBILE_JWT_SECRET_KEY)
	if not secret:
		frappe.throw(
			_("Mobile authentication is not configured. Run the site migration."),
			frappe.AuthenticationError,
		)
	return secret


# endregion MOBILE AUTH CONFIGURATION


# =============================================================================
# region MOBILE CREDENTIAL AND ACCESS STATION
# =============================================================================

def _authenticate_mobile_credentials(email, password):
	if not email or not password:
		frappe.throw(_("Email and password are required."), frappe.AuthenticationError)
	if frappe.get_system_settings("disable_user_pass_login"):
		frappe.throw(_("Password login is disabled for this site."), frappe.AuthenticationError)

	login_manager = frappe.local.login_manager
	login_manager.authenticate(user=email, pwd=password)
	if login_manager.force_user_to_reset_password():
		frappe.throw(_("Reset your password in the browser before signing in here."), frappe.AuthenticationError)
	if should_run_2fa(login_manager.user):
		frappe.throw(_("Two-factor mobile sign-in is not configured for this account."), frappe.AuthenticationError)
	validate_ip_address(login_manager.user)
	login_manager.validate_hour()
	return login_manager.user


def _require_mobile_access(user):
	if user == "Administrator":
		return
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(_("This account is disabled."), frappe.AuthenticationError)
	roles = set(frappe.get_roles(user))
	if not roles.intersection(MOBILE_ROLES):
		frappe.throw(_("Your account does not have access to BulkBite."), frappe.PermissionError)


# endregion MOBILE CREDENTIAL AND ACCESS STATION


# =============================================================================
# region MOBILE TOKEN STATION
# =============================================================================

def _token_hash(token):
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _request_metadata():
	request = getattr(frappe.local, "request", None)
	return {
		"ip_address": getattr(frappe.local, "request_ip", None),
		"user_agent": request.headers.get("User-Agent", "")[:500] if request else "",
	}


def _issue_access_token(user):
	now = datetime.now(UTC)
	return jwt.encode(
		{
			"sub": user,
			"iss": MOBILE_JWT_ISSUER,
			"aud": MOBILE_JWT_AUDIENCE,
			"typ": "access",
			"jti": uuid.uuid4().hex,
			"iat": now,
			"exp": now + timedelta(minutes=MOBILE_ACCESS_TOKEN_MINUTES),
		},
		_get_mobile_jwt_secret(),
		algorithm=MOBILE_JWT_ALGORITHM,
	)


def _create_refresh_session(user, family_id=None, device_name=None):
	refresh_token = secrets.token_urlsafe(48)
	session = frappe.get_doc(
		{
			"doctype": "BulkBite Mobile Auth Session",
			"user": user,
			"token_hash": _token_hash(refresh_token),
			"family_id": family_id or uuid.uuid4().hex,
			"expires_at": add_days(now_datetime(), MOBILE_REFRESH_TOKEN_DAYS),
			"device_name": (device_name or "")[:140],
			"last_used_at": now_datetime(),
			**_request_metadata(),
		}
	)
	session.insert(ignore_permissions=True)
	return session, refresh_token


def _token_response(user, refresh_token):
	return {
		"access_token": _issue_access_token(user),
		"refresh_token": refresh_token,
		"token_type": MOBILE_AUTH_SCHEME,
		"expires_in": MOBILE_ACCESS_TOKEN_MINUTES * 60,
		"user": user,
	}


def _revoke_family(family_id):
	revoked_at = now_datetime()
	for session in frappe.get_all(
		"BulkBite Mobile Auth Session",
		filters={"family_id": family_id},
		fields=["name", "revoked_at"],
	):
		if not session.revoked_at:
			frappe.db.set_value(
				"BulkBite Mobile Auth Session",
				session.name,
				"revoked_at",
				revoked_at,
				update_modified=False,
			)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def login_mobile(email=None, password=None, device_name=None):
	"""Exchange valid BulkBite credentials for a native access/refresh pair."""
	user = _authenticate_mobile_credentials(email, password)
	_require_mobile_access(user)
	_session, refresh_token = _create_refresh_session(user, device_name=device_name)
	frappe.db.commit()
	return _token_response(user, refresh_token)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def refresh_mobile_session(refresh_token=None):
	"""Rotate one valid refresh token and return a new token pair."""
	if not refresh_token:
		frappe.throw(_("A refresh token is required."), frappe.AuthenticationError)

	session_name = frappe.db.get_value(
		"BulkBite Mobile Auth Session", {"token_hash": _token_hash(refresh_token)}, "name"
	)
	if not session_name:
		frappe.throw(_("The mobile session is no longer valid."), frappe.AuthenticationError)

	session = frappe.get_doc("BulkBite Mobile Auth Session", session_name)
	if session.revoked_at:
		if session.replaced_by:
			_revoke_family(session.family_id)
			frappe.db.commit()
		frappe.throw(_("The mobile session is no longer valid."), frappe.AuthenticationError)
	if get_datetime(session.expires_at) <= now_datetime():
		session.db_set("revoked_at", now_datetime(), update_modified=False)
		frappe.db.commit()
		frappe.throw(_("The mobile session has expired. Sign in again."), frappe.AuthenticationError)

	_require_mobile_access(session.user)
	new_session, new_refresh_token = _create_refresh_session(
		session.user,
		family_id=session.family_id,
		device_name=session.device_name,
	)
	session.db_set(
		{
			"revoked_at": now_datetime(),
			"last_used_at": now_datetime(),
			"replaced_by": new_session.name,
		},
		update_modified=False,
	)
	frappe.db.commit()
	return _token_response(session.user, new_refresh_token)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout_mobile(refresh_token=None):
	"""Revoke the refresh-token family used by this installed app session."""
	if refresh_token:
		family_id = frappe.db.get_value(
			"BulkBite Mobile Auth Session",
			{"token_hash": _token_hash(refresh_token)},
			"family_id",
		)
		if family_id:
			_revoke_family(family_id)
			frappe.db.commit()
	return {"ok": True}


# endregion MOBILE TOKEN STATION


# =============================================================================
# region FRAPPE MOBILE AUTH HOOK
# =============================================================================

def validate_mobile_jwt():
	"""Authenticate private BulkBite JWTs without entering Frappe OAuth parsing."""
	if frappe.session.user not in (None, "", "Guest"):
		return
	authorization = frappe.get_request_header("Authorization", "")
	scheme, separator, token = authorization.partition(" ")
	if not separator or scheme.lower() != MOBILE_AUTH_SCHEME.lower() or not token:
		return

	try:
		claims = jwt.decode(
			token,
			_get_mobile_jwt_secret(),
			algorithms=[MOBILE_JWT_ALGORITHM],
			audience=MOBILE_JWT_AUDIENCE,
			issuer=MOBILE_JWT_ISSUER,
			options={"require": ["sub", "iss", "aud", "typ", "jti", "iat", "exp"]},
		)
	except jwt.PyJWTError:
		raise frappe.AuthenticationError

	if claims.get("typ") != "access":
		raise frappe.AuthenticationError
	user = claims.get("sub")
	if not user or not frappe.db.get_value("User", user, "enabled"):
		raise frappe.AuthenticationError
	form_dict = frappe.local.form_dict
	frappe.set_user(user)
	frappe.local.form_dict = form_dict


# endregion FRAPPE MOBILE AUTH HOOK
