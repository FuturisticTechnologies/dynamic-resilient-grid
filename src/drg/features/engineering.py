"""Feature engineering for half-hourly neighbourhood demand.

Produces the design matrix used by every forecaster:

* **calendar** - hour, half-hour period, day of week, month, season, weekend
  and UK bank-holiday flags, plus cyclical (sin/cos) encodings so tree and
  linear models both see the periodicity;
* **statistical** - lags (t-1 ... t-1 week), rolling mean / std / min / max,
  demand ramp rate and acceleration, and same-period-yesterday deltas;

The same routine is used offline (batch training) and online (streaming
replay / API), which removes train-serve skew.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from drg.config import Config
from drg.utils.logging_utils import get_logger

log = get_logger(__name__)

TARGET = "demand_kwh"

# England & Wales bank holidays covering the Low Carbon London study period
# plus the synthetic fallback range.
UK_BANK_HOLIDAYS = pd.to_datetime(
    [
        "2011-01-03",
        "2011-04-22",
        "2011-04-25",
        "2011-04-29",
        "2011-05-02",
        "2011-05-30",
        "2011-08-29",
        "2011-12-26",
        "2011-12-27",
        "2012-01-02",
        "2012-04-06",
        "2012-04-09",
        "2012-05-07",
        "2012-06-04",
        "2012-06-05",
        "2012-08-27",
        "2012-12-25",
        "2012-12-26",
        "2013-01-01",
        "2013-03-29",
        "2013-04-01",
        "2013-05-06",
        "2013-05-27",
        "2013-08-26",
        "2013-12-25",
        "2013-12-26",
        "2014-01-01",
        "2014-04-18",
        "2014-04-21",
        "2014-05-05",
        "2014-05-26",
        "2014-08-25",
        "2014-12-25",
        "2014-12-26",
    ]
)


def _season(month: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [month.isin([12, 1, 2]), month.isin([3, 4, 5]), month.isin([6, 7, 8])],
            ["winter", "spring", "summer"],
            default="autumn",
        ),
        index=month.index,
    )


def add_calendar_features(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    ts = df[ts_col]
    df["hour"] = ts.dt.hour
    df["minute"] = ts.dt.minute
    df["period_of_day"] = ts.dt.hour * 2 + ts.dt.minute // 30
    df["day_of_week"] = ts.dt.dayofweek
    df["day_of_year"] = ts.dt.dayofyear
    df["month"] = ts.dt.month
    df["year"] = ts.dt.year
    df["week_of_year"] = ts.dt.isocalendar().week.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_holiday"] = ts.dt.normalize().isin(UK_BANK_HOLIDAYS).astype(int)
    df["season"] = _season(df["month"])
    df["is_winter"] = df["season"].eq("winter").astype(int)
    df["is_evening_peak"] = df["period_of_day"].between(34, 43).astype(int)  # 17:00-21:30

    # cyclical encodings
    df["sin_period"] = np.sin(2 * np.pi * df["period_of_day"] / 48.0)
    df["cos_period"] = np.cos(2 * np.pi * df["period_of_day"] / 48.0)
    df["sin_dow"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["cos_dow"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    return df


def build_feature_table(
    demand: pd.DataFrame,
    cfg: Config,
    weather: pd.DataFrame | None = None,
    carbon: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Full offline feature table, one row per (timestamp, neighbourhood)."""
    fcfg = cfg.features
    df = demand.sort_values(["neighbourhood_id", "timestamp"]).reset_index(drop=True).copy()
    df = add_calendar_features(df)

    horizon = int(fcfg.get("horizon", 1))
    if horizon > 1:
        df["target"] = df.groupby("neighbourhood_id", observed=True)[TARGET].shift(-(horizon - 1))
    else:
        df["target"] = df[TARGET]

    before = len(df)
    df = df.dropna(subset=["target"] + [c for c in df.columns if c.startswith("lag_")])
    log.info(
        "feature table: %s rows x %s columns (dropped %s warm-up rows)",
        f"{len(df):,}",
        df.shape[1],
        f"{before - len(df):,}",
    )
    return df.reset_index(drop=True)


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model input columns (numeric only, no identifiers or leakage)."""
    exclude = {
        "timestamp",
        "neighbourhood_id",
        "season",
        "source",
        "target",
        TARGET,
        "minute",
        "year",
    }
    cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]
    return cols
