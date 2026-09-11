"""Push warehouse views/results to Google Sheets (a Looker Studio source).

Uses a Google service account (see README "Google Sheets setup"):
  * create the SA in Google Cloud Console, enable Sheets + Drive APIs,
  * download its JSON key to a local path (never commit it),
  * share the target spreadsheet with the SA's email address (Editor),
  * set ADZUNA_GOOGLE_SHEETS_CREDENTIALS (path) and ADZUNA_GOOGLE_SHEETS_KEY.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _cell(value: object) -> str:
    """Stringify one cell for Sheets (blanks for NaN, ints for 2.0)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and not pd.isna(value) and value.is_integer():
        return str(int(value))
    return str(value)


def _frame_to_values(df: pd.DataFrame) -> list[list[str]]:
    """Convert a frame to a list of value-lists (header + rows), Google style."""
    header = [str(c) for c in df.columns]
    if df.empty:
        return [header]
    values = [[_cell(v) for v in row] for row in df.astype(object).values]
    return [header] + values


class SheetsExporter:
    """Exports DataFrames to named worksheets in one spreadsheet.

    ``client`` is injectable for tests; by default it is created from the
    service-account JSON on first use.
    """

    def __init__(self, credentials_path: str, spreadsheet_key: str, client: Any = None) -> None:
        if not credentials_path or not spreadsheet_key:
            raise ValueError(
                "Google Sheets export needs ADZUNA_GOOGLE_SHEETS_CREDENTIALS (service account "
                "JSON path) and ADZUNA_GOOGLE_SHEETS_KEY (spreadsheet id)."
            )
        self.credentials_path = Path(credentials_path)
        self.spreadsheet_key = spreadsheet_key
        self._client = client

    @property
    def client(self) -> Any:  # lazy so credentials are only needed when exporting
        if self._client is None:
            import gspread

            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"Service-account credentials not found: {self.credentials_path}"
                )
            self._client = gspread.service_account(filename=str(self.credentials_path))
        return self._client

    def _worksheet(self, name: str, default_rows: int = 1000, default_cols: int = 26):
        spreadsheet = self.client.open_by_key(self.spreadsheet_key)
        try:
            return spreadsheet.worksheet(name)
        except Exception:
            return spreadsheet.add_worksheet(title=name, rows=default_rows, cols=default_cols)

    def export_df(self, df: pd.DataFrame, worksheet_name: str, *, replace: bool = True) -> None:
        """Write a frame into a worksheet (header + rows)."""
        ws = self._worksheet(worksheet_name)
        values = _frame_to_values(df)
        if replace:
            ws.clear()
            if values:
                ws.update(values, value_input_option="USER_ENTERED")
        else:
            ws.append_rows(values[1:], value_input_option="USER_ENTERED")
        logger.info("Exported %d rows to sheet '%s'", len(values) - 1, worksheet_name)

    def export_all(self, frames: dict[str, pd.DataFrame]) -> list[str]:
        """Export each named frame to a worksheet of the same name."""
        written: list[str] = []
        for name, frame in frames.items():
            self.export_df(frame, name)
            written.append(name)
        return written


def dry_run_preview(frames: dict[str, pd.DataFrame]) -> None:
    """Print frame shapes/samples instead of calling the Sheets API."""
    logger.info("--- dry-run preview (no Google API call) ---")
    for name, frame in frames.items():
        print(f"\n[{name}] shape={frame.shape}")
        with pd.option_context("display.max_columns", 20, "display.width", 160):
            print(frame.head(10).to_string(index=False))


__all__ = ["SheetsExporter", "dry_run_preview", "_frame_to_values"]
