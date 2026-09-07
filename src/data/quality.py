"""Phase 13 — the data-quality gate.

Bad candles poison swings, so validate on ingest. `check_candles` is READ-ONLY and returns a
`QualityReport`; `clean_candles` fixes the mechanical issues (sort, de-dup, drop NaN rows) the
same way `exchange.normalize_ohlcv` does for freshly fetched data — including KEEPING the
volume column (Phase 15 needs it).

`.ok` reflects only UNAMBIGUOUS structural corruption — duplicate timestamps, NaN in OHLC, a
non-monotonic index, or `high < low`. Gaps and outliers are ADVISORY: real markets have
downtime gaps and violent bars, so they are reported but never flip `.ok` and never raise.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

_OHLC = ["open", "high", "low", "close"]
_OHLCV = _OHLC + ["volume"]
# A single-bar close-to-close move larger than this fraction is flagged as a possible
# outlier (advisory only — some real bars genuinely move this much).
_OUTLIER_RETURN = 0.5
# A gap is a bar-to-bar interval more than this multiple of the median interval.
_GAP_FACTOR = 1.5


@dataclass
class QualityReport:
    rows: int
    duplicate_timestamps: int
    nan_rows: int
    monotonic: bool
    invalid_hl: int  # bars with high < low
    gaps: int        # advisory
    outliers: int    # advisory

    @property
    def ok(self) -> bool:
        """True when there is no unambiguous structural corruption (gaps/outliers don't count)."""
        return (
            self.rows > 0
            and self.duplicate_timestamps == 0
            and self.nan_rows == 0
            and self.monotonic
            and self.invalid_hl == 0
        )

    def summary(self) -> str:
        if self.rows == 0:
            return "PROBLEMS: empty candle frame"
        parts = [f"{self.rows} bars"]
        if self.duplicate_timestamps:
            parts.append(f"{self.duplicate_timestamps} duplicate timestamp(s)")
        if self.nan_rows:
            parts.append(f"{self.nan_rows} row(s) with NaN OHLC")
        if not self.monotonic:
            parts.append("index not sorted ascending")
        if self.invalid_hl:
            parts.append(f"{self.invalid_hl} bar(s) with high < low")
        if self.gaps:
            parts.append(f"{self.gaps} time gap(s) [advisory]")
        if self.outliers:
            parts.append(f"{self.outliers} outlier bar(s) [advisory]")
        return f"{'OK' if self.ok else 'PROBLEMS'}: " + ", ".join(parts)


def check_candles(df: pd.DataFrame) -> QualityReport:
    """Read-only inspection of a candle frame. Never mutates `df`."""
    rows = len(df)
    if rows == 0:
        return QualityReport(0, 0, 0, True, 0, 0, 0)

    dup = int(df.index.duplicated().sum())
    present_ohlc = [c for c in _OHLC if c in df.columns]
    nan_rows = int(df[present_ohlc].isna().any(axis=1).sum()) if present_ohlc else 0
    monotonic = bool(df.index.is_monotonic_increasing)

    invalid_hl = 0
    if {"high", "low"}.issubset(df.columns):
        invalid_hl = int((df["high"] < df["low"]).sum())

    # Gaps (advisory): interval derived from the DATA, not by parsing the timeframe string.
    gaps = 0
    if rows >= 3 and isinstance(df.index, pd.DatetimeIndex):
        deltas = df.index.to_series().diff().dropna()
        step = deltas.median()
        if not deltas.empty and step > pd.Timedelta(0):
            gaps = int((deltas > step * _GAP_FACTOR).sum())

    # Outliers (advisory): single-bar moves beyond the threshold.
    outliers = 0
    if "close" in df.columns and rows >= 2:
        pct = df["close"].pct_change().abs()
        outliers = int((pct > _OUTLIER_RETURN).sum())

    return QualityReport(rows, dup, nan_rows, monotonic, invalid_hl, gaps, outliers)


def clean_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Fix mechanical issues WITHOUT dropping columns: drop NaN OHLCV rows, de-dup timestamps
    (keep last), sort ascending. Mirrors `normalize_ohlcv` so a cached frame and a freshly
    fetched one get the same treatment; keeps the volume column.
    """
    present = [c for c in _OHLCV if c in df.columns]
    out = df
    if present:
        out = out.dropna(subset=present)
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()
