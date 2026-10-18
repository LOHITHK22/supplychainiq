"""Public series the pipeline tracks. See docs/data_sources.md for why each one is here."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SeriesSpec:
    series_id: str
    business_use: str


# History before this date is not needed for a two-to-three-year operational dataset,
# and it keeps vintage downloads small.
OBSERVATION_START = date(2015, 1, 1)

FRED_SERIES: tuple[SeriesSpec, ...] = (
    SeriesSpec("ECOMSA", "E-commerce retail sales (quarterly, SA): channel growth context"),
    SeriesSpec("RSNSR", "Advance retail sales, nonstore retailers: closest e-commerce proxy"),
    SeriesSpec("RSXFS", "Advance retail sales ex. food services: overall consumer demand"),
    SeriesSpec("CPIAUCSL", "CPI-U all items: price pressure, deflating revenue"),
    SeriesSpec("UNRATE", "Unemployment rate: consumer health"),
    SeriesSpec("ISRATIO", "Total business inventories/sales ratio: industry benchmark"),
)
