from unittest import TestCase

from bulkbite.truth_ledger import calculate_event_hash, canonicalize_payload


class TestTruthLedgerHashing(TestCase):
	def test_canonical_payload_ignores_dictionary_key_order(self):
		left = {"item": "CHICKEN", "actual": 11, "expected": 10}
		right = {"expected": 10, "actual": 11, "item": "CHICKEN"}
		self.assertEqual(canonicalize_payload(left), canonicalize_payload(right))
		self.assertEqual(calculate_event_hash("prior", left), calculate_event_hash("prior", right))

	def test_previous_hash_changes_event_hash(self):
		payload = {"production_run": "BB-PR-1"}
		self.assertNotEqual(calculate_event_hash("first", payload), calculate_event_hash("second", payload))
