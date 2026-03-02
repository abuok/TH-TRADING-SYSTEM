"""shared/providers/__init__.py — Provider registry."""

from .proxy import ProxyProvider, MockProxyProvider, get_proxy_provider
from .calendar import (
    CalendarProvider,
    MockCalendarProvider,
    ForexFactoryCalendarProvider,
    get_calendar_provider,
)
from .price_quote import (
    PriceQuoteProvider,
    MockPriceQuoteProvider,
    get_price_quote_provider,
)
from .symbol_spec import (
    SymbolSpecProvider,
    MockSymbolSpecProvider,
    get_symbol_spec_provider,
)

__all__ = [
    "ProxyProvider",
    "MockProxyProvider",
    "get_proxy_provider",
    "CalendarProvider",
    "MockCalendarProvider",
    "ForexFactoryCalendarProvider",
    "get_calendar_provider",
    "PriceQuoteProvider",
    "MockPriceQuoteProvider",
    "get_price_quote_provider",
    "SymbolSpecProvider",
    "MockSymbolSpecProvider",
    "get_symbol_spec_provider",
]
