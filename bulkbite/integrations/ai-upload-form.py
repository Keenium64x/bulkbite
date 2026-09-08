from __future__ import annotations

import frappe

from bulkbite.dysium_services import (
	bulkbite_operations_ai_extraction_proposal_service,
	bulkbite_operations_review_decision_service,
	bulkbite_operations_upload_intake_service,
)

# =============================================================================
# region AI UPLOAD FORM INTEGRATION
# =============================================================================


@frappe.whitelist()
def upload_ai_form_file(**kwargs):
	"""Create a review proposal for an uploaded source file."""
	return bulkbite_operations_upload_intake_service(**kwargs)


@frappe.whitelist()
def propose_ai_form_extraction(**kwargs):
	"""Return schema-bound AI extraction output as proposal state only."""
	return bulkbite_operations_ai_extraction_proposal_service(**kwargs)


@frappe.whitelist()
def approve_ai_form_proposal(**kwargs):
	"""Approve a proposal through the backend review decision service."""
	return bulkbite_operations_review_decision_service(decision="approved", **kwargs)


@frappe.whitelist()
def reject_ai_form_proposal(**kwargs):
	"""Reject a proposal without posting records."""
	return bulkbite_operations_review_decision_service(decision="rejected", **kwargs)


# endregion AI UPLOAD FORM INTEGRATION
