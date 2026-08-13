"""Backtest (SPEC §13): the signals measured against FDA's own history.

The FDA list keeps no history, so its past is reconstructed the way
HHS/ASPE did it — Wayback Machine snapshots of the legacy
accessdata.fda.gov CSV (`wayback.py`) — and the lead-time question is
asked of every historical listing: how long before FDA first posted it
did the independent public signals already show the constraint pattern
(`leadtime.py`)?
"""

from .leadtime import lead_time_report
from .wayback import fetch_wayback_history, parse_legacy_csv

__all__ = ["fetch_wayback_history", "lead_time_report", "parse_legacy_csv"]
