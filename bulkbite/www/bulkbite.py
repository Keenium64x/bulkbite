from __future__ import annotations

import frappe
import frappe.sessions


no_cache = 1


# =============================================================================
# region FRONTEND BOOT
# =============================================================================


def get_context(context):
	is_worker_assignment = frappe.local.request.path.rstrip("/") == "/bulkbite/kitchen-assignment"
	if frappe.session.user == "Guest" and not is_worker_assignment:
		frappe.local.flags.redirect_location = "/login?redirect-to=/bulkbite"
		raise frappe.Redirect
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else None,
		"user": frappe.session.user,
		"site_name": frappe.local.site,
	}
	return context


# endregion FRONTEND BOOT
