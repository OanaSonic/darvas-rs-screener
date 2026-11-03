"""Parse manually copied StockCharts SCTR report table text.

No automated scraping, logins or third-party API calls; only parses text
explicitly pasted by the user. Ambiguous lines are ignored rather than guessed.
"""
from __future__ import annotations

import re
from typing import Any

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,10}$")
_SCORE = re.compile(r"^(?:100(?:\.0+)?|\d{1,2}(?:\.\d{1,2})?)$")
_SIGNED = re.compile(r"^[+\-−]\d+(?:\.\d+)?$")
_VOLUME = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d+$")
_CAP = re.compile(r"^\d+(?:\.\d+)?\s*[BMK]?$", re.I)


def _normalize(s: str) -> str:
    return s.replace('\u00a0', ' ').replace('\u202f', ' ').replace('\ufeff', '').strip()


def _val(s: str) -> float | None:
    s = _normalize(s)
    if not _SCORE.fullmatch(s):
        return None
    v = float(s)
    return v if 0 <= v <= 100 else None


def _add(out: dict[str, dict[str, Any]], symbol: str, score: str,
         sector: str = '', industry: str = '') -> bool:
    symbol = _normalize(symbol).upper()
    if not _SYMBOL.fullmatch(symbol) or symbol in {'SCTR', 'SYMBOL', 'TICKER'}:
        return False
    value = _val(score)
    if value is None:
        return False
    row: dict[str, Any] = {'sctr': value}
    if sector:
        row['sector'] = _normalize(sector)
    if industry:
        row['industry'] = _normalize(industry)
    out[symbol.replace('.', '-')] = row
    return True


def _clean_cells(line: str) -> list[str]:
    if '\t' in line:
        cells = [_normalize(c) for c in line.split('\t')]
    elif '|' in line:
        cells = [_normalize(c) for c in line.strip().strip('|').split('|')]
    else:
        return []
    # Chrome may include a leading drag/menu icon or blank column.
    while cells and cells[0] in {'', '≡', '☰', '☷', '☰', '☲', '▤', '⋮', '='}:
        cells.pop(0)
    return cells


def parse_sctr_paste(text: str) -> tuple[dict[str, dict[str, Any]], str]:
    """Read StockCharts free SCTR copy (TSV, pipes, rows or vertical cells).

    Requires an unambiguous ticker, 0-100 SCTR, change, price and volume
    when reading a full report. Two-column 'Ticker SCTR' formats also work.
    """
    out: dict[str, dict[str, Any]] = {}
    lines = [_normalize(s) for s in text.splitlines() if _normalize(s)]
    if not lines:
        return {}, 'Nu ai lipit încă tabelul StockCharts.'

    # Structured browser clipboard: a tabular row per line, sometimes with
    # header Symbol / Name / Sector / Industry / SCTR / Chg / Last / Volume.
    header: dict[str, int] = {}
    for line in lines:
        cells = _clean_cells(line)
        if not cells:
            continue
        lower = [c.casefold() for c in cells]
        if 'symbol' in lower and 'sctr' in lower:
            header = {c: i for i, c in enumerate(lower)}
            continue
        if header and all(i < len(cells) for i in (header.get('symbol', 9999), header.get('sctr', 9999))):
            i = header['symbol']
            j = header['sctr']
            if _add(out, cells[i], cells[j],
                    cells[header['sector']] if 'sector' in header and header['sector'] < len(cells) else '',
                    cells[header['industry']] if 'industry' in header and header['industry'] < len(cells) else ''):
                continue
        if len(cells) >= 9:
            # Report columns after menu icon: Symbol, Name, Sector, Industry,
            # SCTR, Chg, Last, Volume, Market Cap.
            if _SIGNED.fullmatch(cells[5]) and _VOLUME.fullmatch(cells[7]) and _add(out, cells[0], cells[4], cells[2], cells[3]):
                continue
        if len(cells) >= 2 and len(cells) <= 4 and _add(out, cells[0], cells[1]):
            continue

    # Rows rendered as ordinary text (browser without tab preservation).
    # Capture score only if followed by signed change, price, volume, cap.
    pat = re.compile(
        r'(?P<sctr>(?:100(?:\.0+)?|\d{1,2}(?:\.\d{1,2})?))'
        r'\s+(?P<change>[+\-−]\d+(?:\.\d+)?)'
        r'\s+(?P<price>\d+(?:\.\d+)?)'
        r'\s+(?P<volume>\d{1,3}(?:,\d{3})+|\d+)'
        r'\s+(?P<cap>\d+(?:\.\d+)?\s*[BMK])\b', re.I)
    for line in lines:
        if '\t' in line or '|' in line:
            continue
        m = pat.search(line)
        if not m:
            continue
        prefix = line[:m.start()].strip()
        # Only first token is the ticker; remaining tokens are company name,
        # sector and industry (not safely separable without tabs).
        tokens = prefix.replace('≡', ' ').split()
        if len(tokens) >= 2:
            _add(out, tokens[0], m.group('sctr'))

    # Some browsers copy all cells on their own lines (verticalized table).
    # Require a signed change, a price, a volume and a cap so incidental page
    # text cannot masquerade as a SCTR score.
    for i in range(len(lines) - 8):
        cells = lines[i:i+9]
        if (_SYMBOL.fullmatch(cells[0]) and _val(cells[4]) is not None
                and _SIGNED.fullmatch(cells[5])
                and re.fullmatch(r'\d+(?:\.\d+)?', cells[6])
                and _VOLUME.fullmatch(cells[7]) and _CAP.fullmatch(cells[8])):
            _add(out, cells[0], cells[4], cells[2], cells[3])

    if not out:
        return {}, ('Nu am recunoscut rânduri complete cu Ticker și SCTR. '
                    'Selectează rândurile tabelului, copiază-le și lipește-le '
                    'aici. Alternativ, poți lipi 2 coloane separate prin TAB: Ticker și SCTR.')
    return out, f'Au fost identificate {len(out)} tickere cu SCTR real din textul lipit (snapshot manual).'
