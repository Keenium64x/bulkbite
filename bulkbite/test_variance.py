from unittest import TestCase

from bulkbite.variance import calculate_output_variance, calculate_usage_variance


class TestVarianceCalculation(TestCase):
	def test_usage_variance_reports_quantity_percent_and_cost(self):
		result = calculate_usage_variance(10, 12, 4.5)
		self.assertEqual(result["variance_qty"], 2)
		self.assertEqual(result["variance_percent"], 20)
		self.assertEqual(result["expected_cost"], 45)
		self.assertEqual(result["actual_cost"], 54)
		self.assertEqual(result["cost_variance"], 9)

	def test_zero_theory_does_not_divide_by_zero(self):
		result = calculate_usage_variance(0, 2, 5)
		self.assertEqual(result["variance_percent"], 0)
		self.assertEqual(result["cost_variance"], 10)

	def test_output_variance_uses_actual_minus_planned(self):
		result = calculate_output_variance(100, 94)
		self.assertEqual(result["variance_qty"], -6)
		self.assertEqual(result["variance_percent"], -6)
