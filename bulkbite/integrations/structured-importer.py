from __future__ import annotations

import frappe

from bulkbite.dysium_services import (
	bulkbite_operations_import_commit_service,
	bulkbite_operations_import_preview_service,
	bulkbite_operations_import_template_service,
)

# =============================================================================
# region STRUCTURED IMPORTER INTEGRATION
# =============================================================================


@frappe.whitelist()
def validate_import_headers(**kwargs):
	"""Validate supplied workbook headers against the selected template."""
	return bulkbite_operations_import_template_service(**kwargs)


@frappe.whitelist()
def preview_structured_import(**kwargs):
	"""Preview import rows without committing records."""
	return bulkbite_operations_import_preview_service(**kwargs)


@frappe.whitelist()
def apply_structured_import(**kwargs):
	"""Summarize deterministic import commit results for already validated rows."""
	return bulkbite_operations_import_commit_service(**kwargs)


# endregion STRUCTURED IMPORTER INTEGRATION
