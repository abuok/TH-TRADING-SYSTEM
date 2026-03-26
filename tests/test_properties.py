import os
import sys
import hypothesis.strategies as st
from hypothesis import given

# Ensure project root is in sys.path for importing shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.logic.trading_logic import calculate_rr

@given(st.floats(min_value=0.01, max_value=10000), 
       st.floats(min_value=0.01, max_value=10000), 
       st.floats(min_value=0.01, max_value=10000))
def test_calculate_rr_is_sane(entry, target, stop):
    """Ensure that reward-to-risk ratio calculations always yield non-negative results."""
    res = calculate_rr(entry, target, stop)
    assert res >= 0 or res is None
