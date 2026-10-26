import csv
import io
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from fastapi import HTTPException
from fastapi.responses import Response

MAX_EXPORT_ROWS = 50000


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return v


def _safe_text(v):
    # Neutralise spreadsheet formula injection (=, +, -, @ at the start of a text cell).
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def export_response(filename: str, fmt: str, headers: list[str], rows: list[list]) -> Response:
    if len(rows) > MAX_EXPORT_ROWS:
        raise HTTPException(413, f"Export limité à {MAX_EXPORT_ROWS} lignes : affinez les filtres.")
    clean = [[_safe_text(_cell(v)) for v in r] for r in rows]
    if fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for r in clean:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in r])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(headers)
    w.writerows(clean)
    return Response(
        "﻿" + buf.getvalue(),  # BOM so Excel opens UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )
