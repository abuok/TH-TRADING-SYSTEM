# Ingestion Service

## Data Sources

- **Economic Calendar**: [Forex Factory RSS Feed](https://www.forexfactory.com/ff_calendar_thisweek.xml)
    - *Citation*: Data provided by Forex Factory. This feed is used for demonstration purposes.

## Logic

- **Timezone**: All timestamps are normalized to `Africa/Nairobi` (UTC+3).
- **No-Trade Windows**: calculated as +/- 15 minutes around high-impact ('red') events.
- **Emission**: Data is packaged into `MarketContextPacket` and emitted via Redis streams to the `market_context` channel.
