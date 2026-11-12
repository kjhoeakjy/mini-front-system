import pytest

from app.quant.black_scholes import bsm
from app.quant.implied_vol import implied_volatility


@pytest.mark.parametrize("ot", ["CALL", "PUT"])
@pytest.mark.parametrize("sigma", [0.08, 0.2, 0.6, 1.5])
def test_round_trip(ot, sigma):
    args = (100.0, 95.0, 0.5, 0.04, 0.01)
    price = bsm(ot, *args, sigma).price
    r = implied_volatility(price, ot, *args)
    assert r.status == "OK" and r.implied_vol == pytest.approx(sigma, abs=1e-7)


def test_bounds_violation_returns_no_number():
    lo = implied_volatility(4.0, "CALL", 100, 90, 0.5, 0.04, 0.0)   # 내재가치보다 낮은 가격
    hi = implied_volatility(101.0, "CALL", 100, 90, 0.5, 0.04, 0.0)
    assert lo.status == "BELOW_LOWER_BOUND" and lo.implied_vol is None
    assert hi.status == "ABOVE_UPPER_BOUND" and hi.implied_vol is None
    assert implied_volatility(-1, "CALL", 100, 90, 0.5, 0.04, 0.0).status == "INVALID_INPUT"
