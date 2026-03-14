# Ingestion Service

## Data Sources

- **Economic Calendar**: [Forex Factory RSS Feed](https://www.forexfactory.com/ff_calendar_thisweek.xml)
  - *Citation*: Data provided by Forex Factory. Feed for demonstration.

## Logic

- **Timezone**: All timestamps normalized to `Africa/Nairobi` (UTC+3).
- **No-Trade Windows**: +/- 15 minutes around high-impact ('red') events.
- **Emission**: Data is packaged into `MarketContextPacket` and emitted via
  Redis streams to the `market_context` channel.
