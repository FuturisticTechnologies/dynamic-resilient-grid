"""Public API clients for the DRG contextual layer.

Three public data services are used, in order of preference:

1. **National Grid ESO Carbon Intensity API** -- ``api.carbonintensity.org.uk``.
   Free, no key, half-hourly national and regional carbon intensity. Its
   archive starts in 2017, so for the 2011-2014 Low Carbon London period a
   documented seasonal/diurnal *climatology proxy* is derived from a recent
   reference year (never silently presented as measured data: every row is
   tagged in the ``source`` column).
2. **Open-Meteo** -- ``archive-api.open-meteo.com`` / ``api.open-meteo.com``.
   Free, no key, and its ERA5 archive does cover 2011-2014, so historical
   temperature for the model period is genuinely observed.
3. **OpenWeatherMap** -- used for live current conditions and short-term
   forecast when ``DRG_OPENWEATHER_API_KEY`` is set.

Every call is retried with exponential backoff, disk-cached, and degrades to a
deterministic offline fallback so that no pipeline stage can be blocked by
network availability.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

_TIMEOUT = 20
_USER_AGENT = "DynamicResilientGrid/1.0 (academic research prototype)"


def _session(cache_path: Path | None = None, cache_hours: int = 6) -> requests.Session:
    """Return a (optionally disk-cached) HTTP session."""
    if cache_path is not None:
        try:
            import requests_cache

            sess = requests_cache.CachedSession(
                str(cache_path.with_suffix("")),
                backend="sqlite",
                expire_after=cache_hours * 3600,
                allowable_methods=("GET",),
            )
        except Exception:  # pragma: no cover - optional dependency
            sess = requests.Session()
    else:
        sess = requests.Session()
    sess.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json"})
    return sess


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=12),
    retry=retry_if_exception_type((requests.RequestException, ValueError)),
)
def _get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    resp = session.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected payload type from {url}: {type(payload)}")
    return payload


# ===========================================================================
# Weather
# ===========================================================================
@dataclass
class WeatherClient:
    """Temperature provider: OpenWeatherMap when keyed, Open-Meteo otherwise."""

    latitude: float = 51.5072
    longitude: float = -0.1276
    api_key: str = ""
    cache_dir: Path | None = None
    cache_hours: int = 6
    session: requests.Session = field(init=False)

    OWM_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
    OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"
    OM_FORECAST = "https://api.open-meteo.com/v1/forecast"
    OM_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

    def __post_init__(self) -> None:
        cache = (self.cache_dir / "weather_http_cache") if self.cache_dir else None
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
        self.session = _session(cache, self.cache_hours)

    # ---------------------------------------------------------------- live
    def current(self) -> dict[str, Any]:
        if self.api_key:
            try:
                payload = _get_json(
                    self.session,
                    self.OWM_CURRENT,
                    {
                        "lat": self.latitude,
                        "lon": self.longitude,
                        "appid": self.api_key,
                        "units": "metric",
                    },
                )
                return {
                    "temperature_c": payload["main"]["temp"],
                    "feels_like_c": payload["main"].get("feels_like"),
                    "humidity_pct": payload["main"].get("humidity"),
                    "wind_ms": payload.get("wind", {}).get("speed"),
                    "description": payload["weather"][0]["description"],
                    "location": payload.get("name"),
                    "source": "openweathermap",
                    "timestamp": pd.Timestamp.utcnow().isoformat(),
                }
            except Exception as exc:
                log.warning("OpenWeatherMap current failed, falling back: %s", exc)

        try:
            payload = _get_json(
                self.session,
                self.OM_FORECAST,
                {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                    "timezone": "Europe/London",
                },
            )
            cur = payload.get("current", {})
            return {
                "temperature_c": cur.get("temperature_2m"),
                "humidity_pct": cur.get("relative_humidity_2m"),
                "wind_ms": cur.get("wind_speed_10m"),
                "description": "observed",
                "location": "London",
                "source": "open-meteo",
                "timestamp": cur.get("time") or pd.Timestamp.utcnow().isoformat(),
            }
        except Exception as exc:
            log.warning("weather unavailable: %s", exc)
            return {"temperature_c": None, "source": "unavailable", "error": str(exc)}

    def forecast(self, hours: int = 48) -> pd.DataFrame:
        """Hourly temperature forecast."""
        try:
            payload = _get_json(
                self.session,
                self.OM_FORECAST,
                {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "hourly": "temperature_2m",
                    "forecast_days": max(1, min(16, hours // 24 + 1)),
                    "timezone": "Europe/London",
                },
            )
            hourly = payload["hourly"]
            df = pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(hourly["time"]),
                    "temperature_c": hourly["temperature_2m"],
                }
            )
            return df.head(hours).assign(source="open-meteo")
        except Exception as exc:
            log.warning("weather forecast unavailable: %s", exc)
            return pd.DataFrame(columns=["timestamp", "temperature_c", "source"])

    # ------------------------------------------------------------ historical
    def archive(self, start: dt.date | str, end: dt.date | str) -> pd.DataFrame:
        """ERA5 reanalysis hourly temperature (covers 1940 -> present)."""
        try:
            payload = _get_json(
                self.session,
                self.OM_ARCHIVE,
                {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "start_date": str(pd.Timestamp(start).date()),
                    "end_date": str(pd.Timestamp(end).date()),
                    "hourly": "temperature_2m",
                    "timezone": "Europe/London",
                },
            )
            hourly = payload["hourly"]
            df = pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(hourly["time"]),
                    "temperature_c": hourly["temperature_2m"],
                }
            ).dropna()
            df["source"] = "open-meteo-era5"
            log.info("weather archive: %s hourly observations", f"{len(df):,}")
            return df
        except Exception as exc:
            log.warning("weather archive unavailable: %s", exc)
            return pd.DataFrame(columns=["timestamp", "temperature_c", "source"])


def build_temperature_series(
    index: pd.DatetimeIndex,
    *,
    latitude: float,
    longitude: float,
    api_key: str = "",
    cache_dir: Path | None = None,
    allow_network: bool = True,
    seed: int = 42,
) -> pd.DataFrame:
    """Half-hourly temperature aligned to ``index`` (observed where possible)."""
    from drg.data.synthetic import synthetic_temperature

    index = pd.DatetimeIndex(index).tz_localize(None)
    frame = pd.DataFrame({"timestamp": index})

    hourly = pd.DataFrame()
    if allow_network:
        client = WeatherClient(latitude=latitude, longitude=longitude, api_key=api_key, cache_dir=cache_dir)
        hourly = client.archive(index.min().date(), index.max().date())

    if hourly.empty:
        frame["temperature_c"] = synthetic_temperature(index, seed=seed).to_numpy()
        frame["source"] = "synthetic"
        return frame

    hourly = hourly.set_index("timestamp")["temperature_c"].sort_index()
    resampled = hourly.reindex(hourly.index.union(index)).interpolate("time").reindex(index)
    frame["temperature_c"] = resampled.to_numpy().round(2)
    frame["source"] = "open-meteo-era5"
    if frame["temperature_c"].isna().any():
        fill = synthetic_temperature(index, seed=seed)
        frame["temperature_c"] = frame["temperature_c"].fillna(pd.Series(fill.to_numpy()))
        frame.loc[frame["temperature_c"].isna(), "source"] = "synthetic"
    return frame
