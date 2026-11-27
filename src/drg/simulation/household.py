"""Household-level electrification load, superimposed then aggregated once (DRG-80).

Peak diversity only exists between households: two neighbours' EV sessions and
heat-pump cycles rarely line up to the half-hour. Any step that sums a
technology over the neighbourhood *before* the technologies are combined
throws those time offsets away, and the combined EV + heat-pump peak then
comes out (almost exactly) additive -- which is not what happens physically.

This module therefore keeps every simulated load as a ``(periods, households)``
matrix:

1. adopters are drawn per household, independently per technology, so a
   household can own an EV, a heat pump, both or neither;
2. each technology is simulated per household at half-hourly resolution with
   its own household-specific timing;
3. the household profiles are **superimposed per household**, and
4. the neighbourhood total is formed **once, at the end**.

Per-technology neighbourhood series are still reported, but only as an
attribution of the same draws; they are never re-combined into the total.
"""

from __future__ import annotations

import numpy as np

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

PERIODS_PER_DAY = 48
HOURS_PER_PERIOD = 0.5


# ===========================================================================
# adopters
# ===========================================================================
def adopter_mask(n_households: int, adoption: float, rng: np.random.Generator) -> np.ndarray:
    """Boolean mask of the households that adopt a technology.

    ``round(n_households * adoption)`` households are drawn without
    replacement. Each technology uses its own random stream, so the EV owners
    do not depend on the heat-pump adoption level and vice versa (common
    random numbers across scenarios).
    """
    if n_households <= 0:
        return np.zeros(0, dtype=bool)
    adoption = float(np.clip(adoption, 0.0, 1.0))
    n_adopt = int(round(n_households * adoption))
    mask = np.zeros(n_households, dtype=bool)
    if n_adopt:
        mask[rng.permutation(n_households)[:n_adopt]] = True
    return mask
