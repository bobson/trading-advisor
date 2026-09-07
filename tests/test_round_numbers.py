"""Tests for Phase 18 — psychological round-number levels."""

from __future__ import annotations

import pytest

from src.config import load_config
from src.structure.round_numbers import nearest_round_number


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_step_scales_with_price_magnitude(cfg):
    rn = nearest_round_number(79381.62, cfg)
    assert rn.step == 1000.0          # one order of magnitude below ~79k
    assert rn.nearest == 79000.0
    assert rn.is_near                 # ~0.48% away, within the 0.5% default


def test_far_from_round_number_is_not_near(cfg):
    rn = nearest_round_number(79480.0, cfg)  # ~0.60% from 79000
    assert rn.nearest == 79000.0
    assert not rn.is_near
    assert rn.distance_pct > 0.5


def test_none_on_non_positive_price(cfg):
    assert nearest_round_number(0.0, cfg) is None
    assert nearest_round_number(-5.0, cfg) is None
