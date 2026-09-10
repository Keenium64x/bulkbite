from bulkbite.customer_history_bootstrap import apply_known_customer_history_records


def execute():
	"""Install the confirmed first-cycle and next-cycle customer history."""
	apply_known_customer_history_records(required_source=False)
