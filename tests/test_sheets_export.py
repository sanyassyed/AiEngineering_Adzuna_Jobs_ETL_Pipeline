from __future__ import annotations

import pytest

import pandas as pd

from adzuna_etl.sheets_export import SheetsExporter, _frame_to_values


class FakeWorksheet:
    def __init__(self, name: str):
        self.name = name
        self.values: list[list[str]] = []

    def clear(self) -> None:
        self.values = []

    def update(self, values, value_input_option=None):
        self.values = values

    def append_rows(self, rows, value_input_option=None):
        self.values.extend(rows)


class FakeSpreadsheet:
    def __init__(self):
        self.worksheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, name):
        return self.worksheets[name]

    def add_worksheet(self, title, rows, cols):
        self.worksheets[title] = FakeWorksheet(title)
        return self.worksheets[title]


class FakeClient:
    def __init__(self):
        self.spreadsheets = {"KEY": FakeSpreadsheet()}

    def open_by_key(self, key):
        return self.spreadsheets[key]


def test_export_df_writes_header_and_values():
    df = pd.DataFrame({"country": ["gb", "us"], "ai_share": [0.2, 0.35]})
    client = FakeClient()
    exporter = SheetsExporter("creds.json", "KEY", client=client)
    exporter.export_df(df, "ai_share_latest")
    ws = client.spreadsheets["KEY"].worksheets["ai_share_latest"]
    assert ws.values[0] == ["country", "ai_share"]
    assert ws.values[1] == ["gb", "0.2"]
    assert ws.values[2] == ["us", "0.35"]


def test_export_adds_missing_worksheet():
    df = pd.DataFrame({"a": [1]})
    client = FakeClient()
    exporter = SheetsExporter("creds.json", "KEY", client=client)
    exporter.export_df(df, "brand_new_tab")
    assert "brand_new_tab" in client.spreadsheets["KEY"].worksheets


def test_export_requires_credentials():
    with pytest.raises(ValueError):
        SheetsExporter("", "")


def test_frame_to_values_handles_nan():
    df = pd.DataFrame({"a": [None, 2, 2.5]})
    assert _frame_to_values(df) == [["a"], [""], ["2"], ["2.5"]]
