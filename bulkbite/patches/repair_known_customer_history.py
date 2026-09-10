from bulkbite.customer_history_bootstrap import apply_known_customer_history_records


def execute():
	"""Repair empty dated customer rows and apply the reported first-cycle discount."""
	apply_known_customer_history_records(required_source=False)
