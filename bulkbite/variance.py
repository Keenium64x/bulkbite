from __future__ import annotations

from dataclasses import asdict, dataclass


# =============================================================================
# region VARIANCE CALCULATION
# =============================================================================


@dataclass(frozen=True)
class UsageVariance:
	expected_qty: float
	actual_qty: float
	variance_qty: float
	variance_percent: float
	valuation_rate: float
	expected_cost: float
	actual_cost: float
	cost_variance: float


def calculate_usage_variance(expected_qty, actual_qty, valuation_rate=0):
	"""Return a deterministic theory-versus-actual comparison for one ingredient."""
	expected = _number(expected_qty)
	actual = _number(actual_qty)
	rate = _number(valuation_rate)
	variance = actual - expected
	variance_percent = (variance / expected * 100) if expected else 0
	return asdict(
		UsageVariance(
			expected_qty=expected,
			actual_qty=actual,
			variance_qty=variance,
			variance_percent=variance_percent,
			valuation_rate=rate,
			expected_cost=expected * rate,
			actual_cost=actual * rate,
			cost_variance=variance * rate,
		)
	)


def calculate_output_variance(planned_output_qty, actual_output_qty):
	planned = _number(planned_output_qty)
	actual = _number(actual_output_qty)
	variance = actual - planned
	return {
		"planned_output_qty": planned,
		"actual_output_qty": actual,
		"variance_qty": variance,
		"variance_percent": (variance / planned * 100) if planned else 0,
	}


def _number(value):
	return float(value or 0)


# endregion VARIANCE CALCULATION
