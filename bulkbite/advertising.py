"""Permission-aware advertising campaign library for the BulkBite operations app."""

from pathlib import PurePosixPath
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


CAMPAIGN_STATUSES = ("Draft", "In review", "Changes needed", "Approved", "Placed", "Archived")
PROJECT_TYPES = ("Residence", "Instagram", "Meta", "Google Ads", "Cross-channel", "Other")
CHANNELS = ("Physical poster", "Instagram feed", "Instagram story", "Meta feed", "Meta story", "Google Ads", "Other")
RESIDENCES = ("", "Goldfields", "Metanoia", "Huis Visser", "Other")
ASSET_TYPES = ("Poster", "Print pack", "Feed image", "Story image", "Google image", "Preview", "Source", "Copy", "Other")
ASSET_STATUSES = ("Review", "Changes needed", "Approved", "Superseded")
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".zip", ".json", ".txt", ".md"}
READ_ROLES = {"System Manager", "BulkBite Manager", "BulkBite Worker"}
WRITE_ROLES = {"System Manager", "BulkBite Manager"}


def _roles():
	return set(frappe.get_roles(frappe.session.user))


def _require_read_access():
	if not (_roles() & READ_ROLES):
		frappe.throw(_("You do not have permission to view advertising campaigns."), frappe.PermissionError)


def _require_write_access():
	if not (_roles() & WRITE_ROLES):
		frappe.throw(_("Only a BulkBite manager can change advertising campaigns."), frappe.PermissionError)


def _as_dict(value):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return frappe._dict(value or {})


def _clean_url(value, label, required=False):
	value = str(value or "").strip()
	if required and not value:
		frappe.throw(_("{0} is required.").format(label))
	if value:
		parsed = urlparse(value)
		if parsed.scheme not in {"http", "https"} or not parsed.netloc:
			frappe.throw(_("{0} must be a complete http or https URL.").format(label))
	return value


def _validate_choice(value, options, label, required=True):
	value = str(value or "").strip()
	if required and not value:
		frappe.throw(_("{0} is required.").format(label))
	if value not in options:
		frappe.throw(_("{0} is not a supported value.").format(label))
	return value


def _validated_assets(rows):
	validated = []
	for raw in rows or []:
		row = _as_dict(raw)
		file_url = str(row.get("file_url") or "").strip()
		if not file_url:
			continue
		file_doc = frappe.db.get_value(
			"File",
			{"file_url": file_url},
			["name", "file_name", "is_private"],
			as_dict=True,
		)
		if not file_doc:
			frappe.throw(_("Advertising file {0} no longer exists.").format(file_url))
		if not file_doc.is_private:
			frappe.throw(_("Advertising files must be uploaded privately before they are added to a campaign."))
		extension = PurePosixPath(file_doc.file_name or file_url).suffix.lower()
		if extension not in ALLOWED_EXTENSIONS:
			frappe.throw(_("{0} is not an allowed advertising file type.").format(file_doc.file_name))
		validated.append(
			{
				"asset_title": str(row.get("asset_title") or file_doc.file_name or "Advertising asset").strip(),
				"asset_type": _validate_choice(row.get("asset_type") or "Other", ASSET_TYPES, "Asset type"),
				"channel": _validate_choice(row.get("channel") or "Other", CHANNELS, "Asset channel"),
				"format": str(row.get("format") or "").strip(),
				"review_status": _validate_choice(row.get("review_status") or "Review", ASSET_STATUSES, "Asset status"),
				"asset_file": file_url,
				"file_name": file_doc.file_name,
				"destination_url": _clean_url(row.get("destination_url"), "Asset destination"),
				"notes": str(row.get("notes") or "").strip(),
				"_file_doc": file_doc.name,
			}
		)
	return validated


def _serialize_campaign(doc):
	return {
		"name": doc.name,
		"campaign_title": doc.campaign_title,
		"status": doc.status,
		"project_type": doc.project_type,
		"residence": doc.residence,
		"primary_channel": doc.primary_channel,
		"initiative_date": str(doc.initiative_date or ""),
		"concept_summary": doc.concept_summary,
		"qr_destination": doc.qr_destination,
		"digital_destination": doc.digital_destination,
		"reviewer": doc.reviewer,
		"notes": doc.notes,
		"modified": str(doc.modified or ""),
		"assets": [
			{
				"name": row.name,
				"asset_title": row.asset_title,
				"asset_type": row.asset_type,
				"channel": row.channel,
				"format": row.format,
				"review_status": row.review_status,
				"file_url": row.asset_file,
				"file_name": row.file_name,
				"destination_url": row.destination_url,
				"notes": row.notes,
			}
			for row in doc.assets
		],
	}


@frappe.whitelist(methods=["GET"])
def get_advertising_library():
	"""Return a compact library snapshot. Files remain private Frappe attachments."""
	_require_read_access()
	names = frappe.get_all("BulkBite Advertising Campaign", order_by="modified desc", pluck="name")
	campaigns = [_serialize_campaign(frappe.get_doc("BulkBite Advertising Campaign", name)) for name in names]
	return {
		"campaigns": campaigns,
		"can_manage": bool(_roles() & WRITE_ROLES),
		"options": {
			"statuses": CAMPAIGN_STATUSES,
			"project_types": PROJECT_TYPES,
			"channels": CHANNELS,
			"residences": RESIDENCES,
			"asset_types": ASSET_TYPES,
			"asset_statuses": ASSET_STATUSES,
		},
	}


@frappe.whitelist(methods=["POST"])
def save_advertising_campaign(payload=None):
	"""Create or update one campaign and attach its uploaded private files."""
	_require_write_access()
	data = _as_dict(payload)
	name = str(data.get("name") or "").strip()
	doc = frappe.get_doc("BulkBite Advertising Campaign", name) if name else frappe.new_doc("BulkBite Advertising Campaign")
	if name:
		doc.check_permission("write")
	else:
		doc.check_permission("create")

	primary_channel = _validate_choice(data.get("primary_channel"), CHANNELS, "Primary channel")
	project_type = _validate_choice(data.get("project_type"), PROJECT_TYPES, "Project type")
	residence = _validate_choice(data.get("residence") or "", RESIDENCES, "Residence", required=False)
	if project_type == "Residence" and not residence:
		frappe.throw(_("Choose the residence for a residence campaign."))

	assets = _validated_assets(data.get("assets"))
	qr_destination = _clean_url(
		data.get("qr_destination"),
		"Poster QR destination",
		required=primary_channel == "Physical poster",
	)
	digital_destination = _clean_url(data.get("digital_destination"), "Digital destination")

	doc.campaign_title = str(data.get("campaign_title") or "").strip()
	if not doc.campaign_title:
		frappe.throw(_("Campaign title is required."))
	doc.status = _validate_choice(data.get("status") or "Draft", CAMPAIGN_STATUSES, "Campaign status")
	doc.project_type = project_type
	doc.residence = residence
	doc.primary_channel = primary_channel
	doc.initiative_date = getdate(data.get("initiative_date") or nowdate())
	doc.concept_summary = str(data.get("concept_summary") or "").strip()
	doc.qr_destination = qr_destination
	doc.digital_destination = digital_destination
	doc.reviewer = str(data.get("reviewer") or "").strip()
	doc.notes = str(data.get("notes") or "").strip()
	file_names = [asset["_file_doc"] for asset in assets]
	doc.set("assets", [])
	for asset in assets:
		doc.append("assets", {key: value for key, value in asset.items() if key != "_file_doc"})
	doc.save()

	for file_name in file_names:
		frappe.db.set_value(
			"File",
			file_name,
			{"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
			update_modified=False,
		)
	return _serialize_campaign(doc)
