from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.research.pilot import build_pilot_scorecard
from services.research.tuning import generate_tuning_report
from shared.database.models import Base
from shared.utils.metadata import get_git_commit, get_version


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_tuning_report_metadata(db):
    report = generate_tuning_report(db, days_back=1)
    assert report.reproducibility.version == get_version()
    assert report.reproducibility.git_commit == get_git_commit()
    assert report.reproducibility.guardrails_version != ""


def test_pilot_scorecard_metadata(db):
    # build_pilot_scorecard needs some session logs to work properly if we want a full check,
    # but we just want to see if the metadata is attached to the object.
    today = datetime.now(timezone.utc).date()
    scorecard = build_pilot_scorecard(db, today, today)
    assert scorecard.reproducibility.version == get_version()
    assert scorecard.reproducibility.git_commit == get_git_commit()
