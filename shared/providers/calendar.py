"""
shared/providers/calendar.py
CalendarProvider interface — economic calendar events and no-trade windows.

Safe degradation: FAIL CLOSED on total fetch failure (log incident).
"""
import os
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger("CalendarProvider")


class CalendarProvider(ABC):
    """Abstract base for economic calendar providers."""

    @abstractmethod
    def fetch_events(self) -> List[Dict]:
        """
        Return a list of high-impact economic events for the current/next day.
        Each event: {"event": str, "time": ISO str, "currency": str, "impact": "High"|"Medium"}
        Must never raise — return [] and log on total failure.
        """

    def get_no_trade_windows(self, events: List[Dict]) -> List[Dict]:
        """
        Derive no-trade windows from event list (±15 min around each event).
        Returns list of {"event", "start", "end", "impact"} dicts with ISO timestamps.
        """
        import pytz
        target_tz = pytz.timezone("Africa/Nairobi")
        now = datetime.now(target_tz)
        windows = []
        for ev in events:
            try:
                ev_time = datetime.fromisoformat(ev["time"])
                if not ev_time.tzinfo:
                    ev_time = target_tz.localize(ev_time)
                if now <= ev_time <= now + timedelta(hours=24):
                    windows.append({
                        "event": ev["event"],
                        "start": (ev_time - timedelta(minutes=15)).isoformat(),
                        "end":   (ev_time + timedelta(minutes=15)).isoformat(),
                        "impact": ev.get("impact", "High"),
                    })
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("CalendarProvider: skipping malformed event %s — %s", ev, exc)
        return windows


class MockCalendarProvider(CalendarProvider):
    """
    Deterministic mock for CI — returns empty list (no news, all safe by default).
    Tests can subclass and override fetch_events to inject scenarios.
    """

    def fetch_events(self) -> List[Dict]:
        return []


class ForexFactoryCalendarProvider(CalendarProvider):
    """
    Real implementation that reads the ForexFactory RSS feed.
    Replaces the static EconomicCalendar class with proper error handling.
    """

    RSS_URL = "https://www.forexfactory.com/ff_calendar_thisweek.xml"

    def fetch_events(self) -> List[Dict]:
        try:
            import feedparser
            import pytz
            target_tz = pytz.timezone("Africa/Nairobi")
            est_tz = pytz.timezone("US/Eastern")

            feed = feedparser.parse(self.RSS_URL)

            if feed.bozo:
                logger.warning(
                    "CalendarProvider: RSS feed returned a malformed response (bozo=%s).",
                    feed.bozo_exception,
                )

            events: List[Dict] = []
            skipped = 0
            for entry in feed.entries:
                impact = getattr(entry, "impact", "Low")
                if impact != "High":
                    continue

                event_time_str = (
                    getattr(entry, "date", "") + " " + getattr(entry, "time", "")
                ).strip()
                try:
                    dt = datetime.strptime(event_time_str, "%m-%d-%Y %I:%M%p")
                    dt_eat = est_tz.localize(dt).astimezone(target_tz)
                    events.append({
                        "event":    entry.title,
                        "time":     dt_eat.isoformat(),
                        "currency": getattr(entry, "country", "USD"),
                        "impact":   "High",
                    })
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        "CalendarProvider: could not parse event %r — %s. Skipping.",
                        getattr(entry, "title", "?"), exc,
                    )
                    skipped += 1

            logger.info(
                "CalendarProvider: fetched %d high-impact events (%d skipped).",
                len(events), skipped,
            )
            return events

        except Exception as exc:  # noqa: BLE001
            # Total fetch failure — log and return empty so callers fail-closed
            logger.error(
                "CalendarProvider: total fetch failure — %s. "
                "Returning empty event list. Downstream safety gates will treat this as "
                "an unknown/unsafe state.",
                exc,
                exc_info=True,
            )
            return []


def get_calendar_provider() -> CalendarProvider:
    """Factory: select provider from CALENDAR_PROVIDER env var."""
    choice = os.getenv("CALENDAR_PROVIDER", "mock").lower()
    if choice == "mock":
        logger.info("CalendarProvider: using MockCalendarProvider (no external calls).")
        return MockCalendarProvider()
    if choice == "forexfactory":
        logger.info("CalendarProvider: using ForexFactoryCalendarProvider.")
        return ForexFactoryCalendarProvider()
    raise ValueError(
        f"Unknown CALENDAR_PROVIDER value: {choice!r}. Expected 'mock' or 'forexfactory'."
    )
