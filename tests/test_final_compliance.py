import os
import re
from shared.database.models import TicketTradeLink
from shared.types.calibration import Recommendation
from shared.types.tuning import Proposal

def test_terminology_purity():
    """Ensure 'confidence' is eradicated from active source files."""
    forbidden = ["confidence_score"] # we allow 'confidence' in strings/comments if unavoidable, but let's check vars
    
    ignore_dirs = [".git", "__pycache__", "venv", ".pytest_cache", "scripts/v1_demo"]
    
    hits = []
    base_path = os.getcwd()
    
    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith((".py", ".html", ".css")):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if "confidence" in content.lower():
                        # We allow it in comments or as part of a word like 'confidence_interval' 
                        # but we want to catch .confidence or confidence=
                        if re.search(r"(\.confidence|confidence\s*=)", content):
                            hits.append(path)
                            
    # Known allowed: shared/logic/alignment.py (comment only)
    # We'll assert hits is empty or only contains permitted files
    # We also exclude THIS file as it contains the forbidden strings for testing
    filtered_hits = [h for h in hits if "alignment.py" not in h and "test_final_compliance.py" not in h]
    assert not filtered_hits, f"Stale terminology found in: {filtered_hits}"

def test_match_score_standardization():
    """Verify match_score is used in the database model."""
    assert hasattr(TicketTradeLink, "match_score")
    assert not hasattr(TicketTradeLink, "confidence")

def test_conviction_standardization():
    """Verify conviction is used in research and tuning types."""
    # Check Recommendation (calibration.py)
    rec_fields = Recommendation.model_fields
    assert "conviction" in rec_fields
    assert "confidence" not in rec_fields
    
    # Check Proposal (tuning.py)
    prop_fields = Proposal.model_fields
    assert "conviction" in prop_fields
    assert "confidence" not in prop_fields

def test_tradeable_spelling():
    """Ensure TRADEABLE is used consistently (not TRADABLE)."""
    # This is a bit broad, but let's check enums at least
    from shared.types.enums import LockoutState
    assert LockoutState.TRADEABLE.value == "TRADEABLE"
    assert "TRADABLE" not in [s.value for s in LockoutState]
