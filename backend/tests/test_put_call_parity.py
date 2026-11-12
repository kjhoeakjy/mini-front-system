import math

import pytest

from app.quant.black_scholes import bsm


@pytest.mark.parametrize("S", [50.0, 100.0, 180.0])
@pytest.mark.parametrize("T", [0.05, 1.0, 3.0])
@pytest.mark.parametrize("r,q", [(0.05, 0.0), (0.03, 0.02), (-0.01, 0.01)])
@pytest.mark.parametrize("sigma", [0.1, 0.45])
def test_parity(S, T, r, q, sigma):
    K = 100.0
    c, p = bsm("CALL", S, K, T, r, q, sigma).price, bsm("PUT", S, K, T, r, q, sigma).price
    assert abs((c - p) - (S * math.exp(-q * T) - K * math.exp(-r * T))) < 1e-8
