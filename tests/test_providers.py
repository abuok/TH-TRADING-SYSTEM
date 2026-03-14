"""
tests/test_providers.py
Verify:
  1. CI runs without external calls using mock providers.
  2. Missing real provider triggers safe behavior (NotImplementedError / None / failure).
  3. Preflight news-window check fails-closed when no MarketContextPacket is in DB.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import Base, OrderTicket, Packet
from shared.logic.execution_logic import PreflightEngine
from shared.providers.calendar import (
    ForexFactoryCalendarProvider,
    MockCalendarProvider,
    get_calendar_provider,
)
from shared.providers.price_quote import (
    MockPriceQuoteProvider,
    RealPriceQuoteProvider,
    get_price_quote_provider,
)
from shared.providers.proxy import (
    MockProxyProvider,
    RealProxyProvider,
    get_proxy_provider,
)

# ── In-memory DB ──────────────────────────────────────────────────────────────

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── Provider factory env-var tests ───────────────────────────────────────────


class TestProxyProviderFactory:
    def test_default_is_mock(self, monkeypatch):
        monkeypatch.delenv("PROXY_PROVIDER", raising=False)
        provider = get_proxy_provider()
        assert isinstance(provider, MockProxyProvider)

    def test_mock_env(self, monkeypatch):
        monkeypatch.setenv("PROXY_PROVIDER", "mock")
        assert isinstance(get_proxy_provider(), MockProxyProvider)

    def test_real_env(self, monkeypatch):
        monkeypatch.setenv("PROXY_PROVIDER", "real")
        assert isinstance(get_proxy_provider(), RealProxyProvider)

    def test_invalid_env_raises(self, monkeypatch):
        monkeypatch.setenv("PROXY_PROVIDER", "bogus")
        with pytest.raises(ValueError, match="Unknown PROXY_PROVIDER"):
            get_proxy_provider()


class TestCalendarProviderFactory:
    def test_default_is_mock(self, monkeypatch):
        monkeypatch.delenv("CALENDAR_PROVIDER", raising=False)
        assert isinstance(get_calendar_provider(), MockCalendarProvider)

    def test_forexfactory_env(self, monkeypatch):
        monkeypatch.setenv("CALENDAR_PROVIDER", "forexfactory")
        assert isinstance(get_calendar_provider(), ForexFactoryCalendarProvider)

    def test_invalid_env_raises(self, monkeypatch):
        monkeypatch.setenv("CALENDAR_PROVIDER", "nope")
        with pytest.raises(ValueError, match="Unknown CALENDAR_PROVIDER"):
            get_calendar_provider()


class TestPriceQuoteProviderFactory:
    def test_default_is_mock(self, monkeypatch):
        monkeypatch.delenv("PRICE_PROVIDER", raising=False)
        assert isinstance(get_price_quote_provider(), MockPriceQuoteProvider)

    def test_real_env(self, monkeypatch):
        monkeypatch.setenv("PRICE_PROVIDER", "real")
        assert isinstance(get_price_quote_provider(), RealPriceQuoteProvider)


# ── Mock provider behaviour ──────────────────────────────────────────────────


class TestMockProviderBehaviour:
    def test_mock_proxy_is_deterministic(self):
        """Two calls must return identical values — no random-walk."""
        p = MockProxyProvider()
        first = p.get_snapshots()
        second = p.get_snapshots()
        assert first == second, "MockProxyProvider must be deterministic"

    def test_mock_proxy_contains_expected_symbols(self):
        p = MockProxyProvider()
        snaps = p.get_snapshots()
        for sym in ("DXY", "US10Y", "SPX"):
            assert sym in snaps
            assert snaps[sym]["delta_pct"] == 0.00

    def test_mock_calendar_returns_empty(self):
        c = MockCalendarProvider()
        events = c.fetch_events()
        assert events == []

    def test_mock_calendar_no_trade_windows_empty(self):
        c = MockCalendarProvider()
        windows = c.get_no_trade_windows([])
        assert windows == []

    def test_mock_price_quote_unconfigured_returns_none(self):
        p = MockPriceQuoteProvider()
        assert p.get_quote("XAUUSD") is None

    def test_mock_price_quote_configured(self):
        p = MockPriceQuoteProvider(quotes={"XAUUSD": (1999.5, 2000.5)})
        q = p.get_quote("XAUUSD")
        assert q is not None
        assert q.mid == pytest.approx(2000.0)
        assert q.symbol == "XAUUSD"


# ── Real provider stubs trigger safe errors ──────────────────────────────────


class TestRealProviderSafeBehaviour:
    def test_real_proxy_fails_closed_empty_dict(self):
        """Real provider with no key returns empty dict (fail-closed)."""
        p = RealProxyProvider()
        assert p.get_snapshots() == {}

    def test_real_price_raises_not_implemented(self):
        p = RealPriceQuoteProvider()
        with pytest.raises(NotImplementedError):
            p.get_quote("XAUUSD")


# ── Preflight fail-closed when no MarketContextPacket ────────────────────────


class TestPreflightFailClosed:
    def _make_ticket(self, db):
        import uuid

        from shared.database.models import Run

        run = Run(run_id=f"run_{uuid.uuid4().hex[:8]}", status="completed")
        db.add(run)
        db.flush()
        ticket = OrderTicket(
            ticket_id="TKT-TEST01",
            setup_packet_id=0,
            risk_packet_id=0,
            pair="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit_1=2030.0,
            lot_size=0.1,
            risk_usd=100.0,
            risk_pct=1.0,
            rr_tp1=3.0,
            idempotency_key=f"key_{uuid.uuid4().hex}",
            status="IN_REVIEW",
        )
        db.add(ticket)
        db.commit()
        return ticket

    def test_news_window_fails_closed_no_context(self, db):
        """When no MarketContextPacket exists, news_window check MUST be FAIL."""
        ticket = self._make_ticket(db)
        engine = PreflightEngine(db)
        checks = engine.run_checks(ticket, current_price=2000.0, current_spread=1.5)

        news_check = next(c for c in checks if c.id == "news_window")
        assert news_check.status == "FAIL", (
            "news_window must FAIL CLOSED when no MarketContextPacket is in DB"
        )
        assert (
            "FAIL-CLOSED" in news_check.details
            or "fail-closed" in news_check.details.lower()
        )

    def test_news_window_passes_with_no_active_window(self, db):
        """When context exists with no active window, check should PASS."""
        import uuid

        from shared.database.models import Run

        ticket = self._make_ticket(db)

        run = Run(run_id=f"run_{uuid.uuid4().hex[:8]}", status="completed")
        db.add(run)
        db.flush()

        # Packet with no_trade_windows that are in the past
        past_window = {
            "event": "Old Event",
            "start": "2000-01-01T00:00:00+03:00",
            "end": "2000-01-01T01:00:00+03:00",
        }
        p = Packet(
            run_id=run.id,
            packet_type="MarketContextPacket",
            schema_version="1.0.0",
            data={"no_trade_windows": [past_window]},
        )
        db.add(p)
        db.commit()

        engine = PreflightEngine(db)
        checks = engine.run_checks(ticket, current_price=2000.0, current_spread=1.5)
        news_check = next(c for c in checks if c.id == "news_window")
        assert news_check.status == "PASS"

    def test_incident_logged_on_missing_context(self, db):
        """An IncidentLog entry must be written when context is absent."""
        ticket = self._make_ticket(db)
        engine = PreflightEngine(db)
        engine.run_checks(ticket, current_price=2000.0, current_spread=1.5)

        from shared.database.models import IncidentLog

        incident = db.query(IncidentLog).first()
        assert incident is not None
        assert incident.severity == "WARNING"
        assert "MarketContextPacket" in incident.message
