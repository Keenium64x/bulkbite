from __future__ import annotations

import frappe
import frappe.sessions


no_cache = 1


# =============================================================================
# region FRONTEND BOOT
# =============================================================================


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/bulkbite"
		raise frappe.Redirect
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"user": frappe.session.user,
		"site_name": frappe.local.site,
	}
	return context


# endregion FRONTEND BOOT
