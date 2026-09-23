"""Permission-aware advertising operations workspace for BulkBite."""

from pathlib import PurePosixPath
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate


CAMPAIGN_STATUSES = ("Draft", "In review", "Changes needed", "Approved", "Placed", "Archived")
REQUEST_STATUSES = ("New", "Ready", "Needs input", "In production", "In review", "Complete", "Cancelled")
PRIORITIES = ("Low", "Normal", "High", "Urgent")
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


def _can_manage():
	return bool(_roles() & WRITE_ROLES)


def _require_read_access():
	if not (_roles() & READ_ROLES):
		frappe.throw(_("You do not have permission to view advertising work."), frappe.PermissionError)


def _require_write_access():
	if not _can_manage():
		frappe.throw(_("Only a BulkBite manager can change campaigns, reviews, or placements."), frappe.PermissionError)


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
		file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name", "is_private"], as_dict=True)
		if not file_doc:
			frappe.throw(_("Advertising file {0} no longer exists.").format(file_url))
		if not file_doc.is_private:
			frappe.throw(_("Advertising files must be uploaded privately before they are added to a campaign."))
		extension = PurePosixPath(file_doc.file_name or file_url).suffix.lower()
		if extension not in ALLOWED_EXTENSIONS:
			frappe.throw(_("{0} is not an allowed advertising file type.").format(file_doc.file_name))
		validated.append({
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
		})
	return validated


def _serialize_request(doc):
	return {field: getattr(doc, field, None) for field in (
		"name", "request_title", "status", "priority", "requested_by", "project_type", "residence",
		"primary_channel", "formats", "meal", "need", "pain_point", "exact_wording", "qr_destination",
		"digital_destination", "reviewer", "notes", "campaign",
	)} | {
		"request_date": str(doc.request_date or ""),
		"due_date": str(doc.due_date or ""),
		"modified": str(doc.modified or ""),
	}


def _serialize_campaign(doc):
	data = {field: getattr(doc, field, None) for field in (
		"name", "source_request", "campaign_title", "status", "project_type", "residence", "primary_channel",
		"audience", "objective", "pain_point", "hook", "concept_summary", "qr_destination", "digital_destination",
		"reviewer", "approval_notes", "notes",
	)}
	data.update({
		"initiative_date": str(doc.initiative_date or ""),
		"due_date": str(doc.due_date or ""),
		"owner": doc.owner_user,
		"modified": str(doc.modified or ""),
		"assets": [{
			"name": row.name, "asset_title": row.asset_title, "asset_type": row.asset_type,
			"channel": row.channel, "format": row.format, "review_status": row.review_status,
			"file_url": row.asset_file, "file_name": row.file_name,
			"destination_url": row.destination_url, "notes": row.notes,
		} for row in doc.assets],
		"placements": [{
			"name": row.name, "channel": row.channel, "location": row.location,
			"placement_date": str(row.placement_date or ""), "quantity": cint(row.quantity), "spend": flt(row.spend),
			"impressions": cint(row.impressions), "clicks": cint(row.clicks), "scans": cint(row.scans),
			"leads": cint(row.leads), "evidence_file": row.evidence_file, "notes": row.notes,
		} for row in doc.placements],
	})
	return data


def _workspace_payload():
	request_names = frappe.get_all("BulkBite Advertising Request", order_by="modified desc", pluck="name")
	campaign_names = frappe.get_all("BulkBite Advertising Campaign", order_by="modified desc", pluck="name")
	requests = [_serialize_request(frappe.get_doc("BulkBite Advertising Request", name)) for name in request_names]
	campaigns = [_serialize_campaign(frappe.get_doc("BulkBite Advertising Campaign", name)) for name in campaign_names]
	assets = [{**asset, "campaign": campaign["name"], "campaign_title": campaign["campaign_title"], "campaign_status": campaign["status"]} for campaign in campaigns for asset in campaign["assets"]]
	placements = [{**placement, "campaign": campaign["name"], "campaign_title": campaign["campaign_title"]} for campaign in campaigns for placement in campaign["placements"]]
	return {
		"requests": requests,
		"campaigns": campaigns,
		"assets": assets,
		"placements": placements,
		"review_queue": [campaign for campaign in campaigns if campaign["status"] in {"In review", "Changes needed"} or any(asset["review_status"] in {"Review", "Changes needed"} for asset in campaign["assets"])],
		"metrics": {
			"open_requests": sum(request["status"] not in {"Complete", "Cancelled"} for request in requests),
			"active_campaigns": sum(campaign["status"] not in {"Placed", "Archived"} for campaign in campaigns),
			"awaiting_review": sum(campaign["status"] in {"In review", "Changes needed"} for campaign in campaigns),
			"approved_assets": sum(asset["review_status"] == "Approved" for asset in assets),
			"placements": sum(placement["quantity"] for placement in placements),
			"spend": sum(placement["spend"] for placement in placements),
			"scans": sum(placement["scans"] for placement in placements),
			"clicks": sum(placement["clicks"] for placement in placements),
		},
		"can_manage": _can_manage(),
		"options": {
			"request_statuses": REQUEST_STATUSES, "priorities": PRIORITIES, "statuses": CAMPAIGN_STATUSES,
			"project_types": PROJECT_TYPES, "channels": CHANNELS, "residences": RESIDENCES,
			"asset_types": ASSET_TYPES, "asset_statuses": ASSET_STATUSES,
		},
	}


@frappe.whitelist(methods=["GET"])
def get_advertising_workspace():
	_require_read_access()
	return _workspace_payload()


@frappe.whitelist(methods=["GET"])
def get_advertising_library():
	workspace = get_advertising_workspace()
	return {"campaigns": workspace["campaigns"], "can_manage": workspace["can_manage"], "options": workspace["options"]}


@frappe.whitelist(methods=["POST"])
def save_advertising_request(payload=None):
	_require_read_access()
	data = _as_dict(payload)
	name = str(data.get("name") or "").strip()
	doc = frappe.get_doc("BulkBite Advertising Request", name) if name else frappe.new_doc("BulkBite Advertising Request")
	if name and not _can_manage() and doc.requested_by != frappe.session.user:
		frappe.throw(_("You can only edit advertising requests you created."), frappe.PermissionError)
	project_type = _validate_choice(data.get("project_type"), PROJECT_TYPES, "Project type")
	residence = _validate_choice(data.get("residence") or "", RESIDENCES, "Residence", required=False)
	if project_type == "Residence" and not residence:
		frappe.throw(_("Choose the residence for a residence request."))
	primary_channel = _validate_choice(data.get("primary_channel"), CHANNELS, "Primary channel")
	doc.request_title = str(data.get("request_title") or "").strip()
	doc.need = str(data.get("need") or "").strip()
	if not doc.request_title or not doc.need:
		frappe.throw(_("Request title and what you need are required."))
	doc.status = _validate_choice(data.get("status") or (doc.status if name else "New"), REQUEST_STATUSES, "Request status")
	if not _can_manage() and doc.status not in {"New", "Ready", "Needs input"}:
		doc.status = "Ready"
	doc.priority = _validate_choice(data.get("priority") or "Normal", PRIORITIES, "Priority")
	doc.request_date = getdate(data.get("request_date") or doc.request_date or nowdate())
	doc.due_date = getdate(data.get("due_date")) if data.get("due_date") else None
	doc.requested_by = doc.requested_by or frappe.session.user
	doc.project_type = project_type
	doc.residence = residence
	doc.primary_channel = primary_channel
	doc.formats = str(data.get("formats") or "").strip()
	doc.meal = str(data.get("meal") or "").strip()
	doc.pain_point = str(data.get("pain_point") or "").strip()
	doc.exact_wording = str(data.get("exact_wording") or "").strip()
	doc.qr_destination = _clean_url(data.get("qr_destination"), "Poster QR destination")
	doc.digital_destination = _clean_url(data.get("digital_destination"), "Digital destination")
	doc.reviewer = str(data.get("reviewer") or "").strip()
	doc.notes = str(data.get("notes") or "").strip()
	doc.save(ignore_permissions=True)
	return _serialize_request(doc)


@frappe.whitelist(methods=["POST"])
def start_advertising_request(name):
	_require_write_access()
	request = frappe.get_doc("BulkBite Advertising Request", name)
	if request.campaign:
		return _serialize_campaign(frappe.get_doc("BulkBite Advertising Campaign", request.campaign))
	if request.primary_channel == "Physical poster" and not request.qr_destination:
		frappe.throw(_("Record the exact registered poster QR destination before starting production."))
	campaign = frappe.new_doc("BulkBite Advertising Campaign")
	campaign.update({
		"source_request": request.name, "campaign_title": request.request_title, "status": "Draft",
		"project_type": request.project_type, "residence": request.residence, "primary_channel": request.primary_channel,
		"initiative_date": nowdate(), "due_date": request.due_date, "audience": "Stellenbosch university students",
		"objective": request.need, "pain_point": request.pain_point, "concept_summary": request.need,
		"qr_destination": request.qr_destination, "digital_destination": request.digital_destination,
		"owner_user": frappe.session.user, "reviewer": request.reviewer, "notes": request.notes,
	})
	campaign.insert()
	request.campaign = campaign.name
	request.status = "In production"
	request.save(ignore_permissions=True)
	return _serialize_campaign(campaign)


@frappe.whitelist(methods=["GET"])
def get_advertising_request_brief(name):
	_require_read_access()
	request = frappe.get_doc("BulkBite Advertising Request", name)
	destination_label = "Exact poster QR" if request.primary_channel == "Physical poster" else "Clickable destination"
	destination = request.qr_destination if request.primary_channel == "Physical poster" else request.digital_destination
	lines = [
		f"Start advertising request {request.name}: {request.request_title}", f"Need: {request.need}",
		f"Project: {request.project_type}" + (f" / {request.residence}" if request.residence else ""),
		f"Primary channel: {request.primary_channel}", f"Formats: {request.formats or 'Use the channel factory default'}",
		f"Priority: {request.priority}; due {request.due_date or 'not set'}",
		f"Meal truth lock: {request.meal or 'Must be confirmed before hero generation'}",
		f"One pain point: {request.pain_point or 'Develop one from the stated need'}",
		f"Exact wording: {request.exact_wording or 'None supplied; create concise review copy'}",
		f"{destination_label}: {destination or ('HOLD-QR' if request.primary_channel == 'Physical poster' else 'Not supplied')}",
		f"Reviewer: {request.reviewer or 'Faith or French before release'}", f"Notes: {request.notes or 'None'}",
		"Use the BulkBite Advertisements factory, food-visual-truth rules, official assets, and fast draft-to-final pipeline. Create review drafts only; do not publish, print, spend, or imply approval.",
	]
	return {"name": request.name, "brief": "\n".join(lines)}


@frappe.whitelist(methods=["POST"])
def save_advertising_campaign(payload=None):
	_require_write_access()
	data = _as_dict(payload)
	name = str(data.get("name") or "").strip()
	doc = frappe.get_doc("BulkBite Advertising Campaign", name) if name else frappe.new_doc("BulkBite Advertising Campaign")
	primary_channel = _validate_choice(data.get("primary_channel"), CHANNELS, "Primary channel")
	project_type = _validate_choice(data.get("project_type"), PROJECT_TYPES, "Project type")
	residence = _validate_choice(data.get("residence") or "", RESIDENCES, "Residence", required=False)
	if project_type == "Residence" and not residence:
		frappe.throw(_("Choose the residence for a residence campaign."))
	assets = _validated_assets(data.get("assets"))
	qr_destination = _clean_url(data.get("qr_destination"), "Poster QR destination", required=primary_channel == "Physical poster")
	doc.source_request = str(data.get("source_request") or doc.source_request or "").strip()
	doc.campaign_title = str(data.get("campaign_title") or "").strip()
	if not doc.campaign_title:
		frappe.throw(_("Campaign title is required."))
	doc.status = _validate_choice(data.get("status") or "Draft", CAMPAIGN_STATUSES, "Campaign status")
	doc.project_type, doc.residence, doc.primary_channel = project_type, residence, primary_channel
	doc.initiative_date = getdate(data.get("initiative_date") or nowdate())
	doc.due_date = getdate(data.get("due_date")) if data.get("due_date") else None
	for field in ("audience", "objective", "pain_point", "hook", "concept_summary", "reviewer", "approval_notes", "notes"):
		setattr(doc, field, str(data.get(field) or "").strip())
	doc.owner_user = str(data.get("owner") or doc.owner_user or frappe.session.user).strip()
	doc.qr_destination = qr_destination
	doc.digital_destination = _clean_url(data.get("digital_destination"), "Digital destination")
	file_names = [asset["_file_doc"] for asset in assets]
	doc.set("assets", [])
	for asset in assets:
		doc.append("assets", {key: value for key, value in asset.items() if key != "_file_doc"})
	doc.save()
	for file_name in file_names:
		frappe.db.set_value("File", file_name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}, update_modified=False)
	return _serialize_campaign(doc)


@frappe.whitelist(methods=["POST"])
def review_advertising_campaign(name, outcome, notes=""):
	_require_write_access()
	if outcome not in {"Approved", "Changes needed"}:
		frappe.throw(_("Review outcome must be Approved or Changes needed."))
	doc = frappe.get_doc("BulkBite Advertising Campaign", name)
	doc.status = outcome
	doc.approval_notes = str(notes or "").strip()
	for asset in doc.assets:
		if asset.review_status != "Superseded":
			asset.review_status = outcome
	doc.save()
	if doc.source_request:
		frappe.db.set_value("BulkBite Advertising Request", doc.source_request, "status", "Complete" if outcome == "Approved" else "In review")
	return _serialize_campaign(doc)


@frappe.whitelist(methods=["POST"])
def save_advertising_placement(campaign, payload=None):
	_require_write_access()
	data = _as_dict(payload)
	doc = frappe.get_doc("BulkBite Advertising Campaign", campaign)
	evidence_file = str(data.get("evidence_file") or "").strip()
	if evidence_file:
		file_doc = frappe.db.get_value("File", {"file_url": evidence_file}, ["name", "is_private"], as_dict=True)
		if not file_doc or not file_doc.is_private:
			frappe.throw(_("Placement evidence must be an existing private file."))
	doc.append("placements", {
		"channel": _validate_choice(data.get("channel") or doc.primary_channel, CHANNELS, "Placement channel"),
		"location": str(data.get("location") or "").strip(), "placement_date": getdate(data.get("placement_date") or nowdate()),
		"quantity": max(0, cint(data.get("quantity"))), "spend": max(0, flt(data.get("spend"))),
		"impressions": max(0, cint(data.get("impressions"))), "clicks": max(0, cint(data.get("clicks"))),
		"scans": max(0, cint(data.get("scans"))), "leads": max(0, cint(data.get("leads"))),
		"evidence_file": evidence_file, "notes": str(data.get("notes") or "").strip(),
	})
	if cint(data.get("quantity")) > 0 or data.get("placement_date"):
		doc.status = "Placed"
	doc.save()
	return _serialize_campaign(doc)
