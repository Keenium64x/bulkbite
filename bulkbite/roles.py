import frappe

from bulkbite.mobile import setup_mobile_jwt_secret


# =============================================================================
# region BULKBITE SITE SETUP
# =============================================================================


ROLE_DEFINITIONS = {
	"BulkBite Worker": "Record receipts, production measurements, worker documents, and physical counts.",
	"BulkBite Manager": "Maintain stock masters, approve production and reconciliation, and export operational records.",
	"BulkBite Accountant": "Read and export reviewed receipt, stock, and evidence records without posting stock.",
}
APP_LOGO_URL = "/assets/bulkbite/images/bulkbite-logo-wordmark.svg"
FAVICON_URL = "/assets/bulkbite/images/bulkbite-icon.svg"


def ensure_bulkbite_setup():
	"""Apply the idempotent roles, branding, and native-auth site contract."""
	ensure_bulkbite_roles()
	ensure_bulkbite_branding()
	setup_mobile_jwt_secret()


def ensure_bulkbite_roles():
	"""Create the project-owned roles referenced by BulkBite permissions."""
	for role_name, description in ROLE_DEFINITIONS.items():
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"disabled": 0,
				"description": description,
			}
		).insert(ignore_permissions=True)


def ensure_bulkbite_branding():
	"""Use the approved BulkBite identity on Frappe login and website surfaces."""
	for fieldname, value in {"app_logo": APP_LOGO_URL, "favicon": FAVICON_URL}.items():
		if frappe.db.get_single_value("Website Settings", fieldname) == value:
			continue
		frappe.db.set_single_value("Website Settings", fieldname, value)


# endregion BULKBITE SITE SETUP
