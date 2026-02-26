import feedparser
import pytz
from datetime import datetime, timedelta
from typing import List, Dict
import os

class EconomicCalendar:
    # Source: Forex Factory RSS Feed
    RSS_URL = "https://www.forexfactory.com/ff_calendar_thisweek.xml"
    TARGET_TZ = pytz.timezone("Africa/Nairobi")

    @classmethod
    def fetch_events(cls) -> List[Dict]:
        """Fetch economic events from the RSS feed."""
        feed = feedparser.parse(cls.RSS_URL)
        events = []
        for entry in feed.entries:
            # Forex Factory RSS items have specific tags
            # We filter for 'High' impact events (usually denoted in the description or via specific tags if using a different API)
            # In RSS, impact is often in the 'impact' tag if parsed correctly, or we can look at the title.
            # For this MVP, we assume all parsed events for now and filter for 'High' if tag exists.
            
            impact = getattr(entry, 'impact', 'Low')
            if impact != 'High':
                continue

            event_time_str = getattr(entry, 'date', '') + ' ' + getattr(entry, 'time', '')
            # Example: Feb 26 2026 8:30am
            try:
                # Forex Factory RSS uses EST/EDT usually
                est_tz = pytz.timezone("US/Eastern")
                dt = datetime.strptime(event_time_str, "%m-%d-%Y %I:%M%p")
                dt_est = est_tz.localize(dt)
                dt_nairobi = dt_est.astimezone(cls.TARGET_TZ)
                
                events.append({
                    "title": entry.title,
                    "impact": impact,
                    "time_nairobi": dt_nairobi,
                    "currency": getattr(entry, 'country', 'USD')
                })
            except Exception:
                continue
                
        return events

    @classmethod
    def get_no_trade_windows(cls, events: List[Dict]) -> List[Dict]:
        """Calculate no-trade windows around high-impact events."""
        windows = []
        now = datetime.now(cls.TARGET_TZ)
        
        for event in events:
            # Check if event is in the next 24h
            if now <= event["time_nairobi"] <= now + timedelta(hours=24):
                start = event["time_nairobi"] - timedelta(minutes=15)
                end = event["time_nairobi"] + timedelta(minutes=15)
                windows.append({
                    "event": event["title"],
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "impact": "High"
                })
        return windows
