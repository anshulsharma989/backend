"""CSV parser.

Rows are grouped into segments, each prefixed with the column headers so
every chunk stays self-describing for retrieval.
"""

from pathlib import Path

import pandas as pd

from app.services.ingestion.parsers.base import BaseParser, ParsedSegment, register_parser

ROWS_PER_SEGMENT = 20


@register_parser("csv")
class CsvParser(BaseParser):
    def parse(self, path: Path) -> list[ParsedSegment]:
        df = pd.read_csv(path)
        headers = ", ".join(str(c) for c in df.columns)
        segments: list[ParsedSegment] = []
        for start in range(0, len(df), ROWS_PER_SEGMENT):
            block = df.iloc[start : start + ROWS_PER_SEGMENT]
            lines = [f"Columns: {headers}"]
            for _, row in block.iterrows():
                lines.append("; ".join(f"{col}: {row[col]}" for col in df.columns))
            segments.append(ParsedSegment(text="\n".join(lines)))
        return segments
