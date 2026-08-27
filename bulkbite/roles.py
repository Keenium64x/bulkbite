import frappe

from bulkbite.mobile import setup_mobile_jwt_secret


# =============================================================================
# region BULKBITE ROLE SETUP
# =============================================================================


ROLE_DEFINITIONS = {
	"BulkBite Worker": "Record receipts, production measurements, worker documents, and physical counts.",
	"BulkBite Manager": "Maintain stock masters, approve production and reconciliation, and export operational records.",
	"BulkBite Accountant": "Read and export reviewed receipt, stock, and evidence records without posting stock.",
}


def ensure_bulkbite_roles():
	"""Create the project-owned roles referenced by BulkBite DocType permissions."""
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
	setup_mobile_jwt_secret()


# endregion BULKBITE ROLE SETUP
