import hypothesis.strategies as st
from hypothesis import given
from shared.logic.trading_logic import calculate_rr

@given(st.floats(min_value=0.01, max_value=10000), 
       st.floats(min_value=0.01, max_value=10000), 
       st.floats(min_value=0.01, max_value=10000))
def test_calculate_rr_is_sane(entry, target, stop):
    """Ensure that reward-to-risk ratio calculations always yield non-negative results."""
    # This assumes calculate_rr handles these inputs without crashing
    res = calculate_rr(entry, target, stop)
    assert res >= 0 or res is None
