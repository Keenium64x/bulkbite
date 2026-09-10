from __future__ import annotations

import re


# =============================================================================
# region REPORTING EVIDENCE SCOPE
# =============================================================================


DEMO_MARKER = re.compile(r"\bDEMO\b", re.IGNORECASE)


def is_demo_evidence(row, *fieldnames):
	"""Return whether a reporting record is explicitly marked as demonstration data."""
	for fieldname in fieldnames:
		value = row.get(fieldname) if hasattr(row, "get") else getattr(row, fieldname, None)
		if DEMO_MARKER.search(str(value or "")):
			return True
	return False


# endregion REPORTING EVIDENCE SCOPE
