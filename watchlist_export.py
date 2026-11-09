"""Pure, tested watchlist exporters for TradingView, Deepvue and thinkorswim.

No credentials, external requests or inferred exchange listings. Data sources are
scan results and user-provided or verified exchange mappings only.
"""
from __future__ import annotations

import csv
from io import StringIO
import math
import re
from typing import Iterable, Mapping

TICKER_RE = re.compile(r"[A-Z^][A-Z0-9.^-]{0,19}\Z")

DETAIL_FIELDS = [
    'ticker', 'exchange', 'pattern', 'status', 'signal_date', 'signal_age_bars',
    'sctr', 'rs_3m', 'rs_percentile', 'rs_new_high', 'close', 'current_close',
    'box_top', 'box_bottom', 'box_pct', 'bars', 'distance_pct', 'risk_pct',
    'entry', 'stop', 'breakout_date', 'weeks_after_breakout', 'advance_pct',
    'ma_kind', 'ma_distance_pct', 'touch_date', 'contraction_ratio',
    'volume_ratio', 'sector', 'industry',
]

EXCHANGE_TO_TV = {
    'NASDAQ':'NASDAQ', 'NMS':'NASDAQ', 'NCM':'NASDAQ', 'NGM':'NASDAQ',
    'NYQ':'NYSE', 'NYSE':'NYSE', 'NYE':'NYSE',
    'AMEX':'AMEX', 'ASE':'AMEX', 'AMERICAN':'AMEX',
    # TradingView ordinarily groups NYSE Arca ETFs under AMEX, e.g. AMEX:SPY.
    'NYSE ARCA':'AMEX', 'ARCA':'AMEX', 'PCX':'AMEX',
}


def clean_symbol(value: object) -> str | None:
    if value is None: return None
    symbol = str(value).strip().upper()
    return symbol if TICKER_RE.fullmatch(symbol) else None


def unique_symbols(records: Iterable[Mapping]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for record in records:
        sym = clean_symbol(record.get('ticker'))
        if sym and sym not in seen:
            seen.add(sym)
            result.append(sym)
    return result


def pattern_label(row: Mapping) -> str:
    name = str(row.get('pattern') or '')
    if name.startswith('VCP'): return 'VCP / Tight Base'
    if name.startswith('First pullback'): return 'First Pullback EMA 20W'
    if name == 'Darvas': return 'Darvas Box'
    return 'Univers SCTR' if name == 'Universe' else name or 'Necunoscut'


def _number(value) -> float | None:
    if value is None or value == '': return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def filter_rows(records: Iterable[Mapping], *, statuses: Iterable[str] = (),
                patterns: Iterable[str] = (), text: str = '',
                sctr_floor: float | None = None, rs_floor: float | None = None,
                max_risk: float | None = None, max_age: int | None = None) -> list[dict]:
    statuses, patterns = set(statuses), set(patterns)
    term = text.strip().upper()
    out = []
    for row in records:
        if statuses and str(row.get('status')) not in statuses: continue
        if patterns and pattern_label(row) not in patterns: continue
        if term and term not in str(row.get('ticker', '')).upper(): continue
        if sctr_floor is not None and (_number(row.get('sctr')) is None or _number(row.get('sctr')) < sctr_floor): continue
        if rs_floor is not None and (_number(row.get('rs_3m')) is None or _number(row.get('rs_3m')) < rs_floor): continue
        if max_risk is not None and (_number(row.get('risk_pct')) is None or _number(row.get('risk_pct')) > max_risk): continue
        if max_age is not None and (_number(row.get('signal_age_bars')) is None or _number(row.get('signal_age_bars')) > max_age): continue
        out.append(dict(row))
    return out


def csv_bytes(records: Iterable[Mapping], fields: list[str] | None = None) -> bytes:
    names = fields or DETAIL_FIELDS
    output = StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=names, extrasaction='ignore', lineterminator='\r\n')
    writer.writeheader()
    for row in records:
        writer.writerow({k: row.get(k, '') if row.get(k) is not None else '' for k in names})
    return output.getvalue().encode('utf-8-sig')


def thinkorswim_csv(records: Iterable[Mapping]) -> bytes:
    """A watchlist-ready CSV with the standard single Symbol header."""
    return csv_bytes(({'Symbol': s} for s in unique_symbols(records)), ['Symbol'])


def deepvue_text(records: Iterable[Mapping]) -> str:
    """Deepvue's documented Add Symbol bulk paste accepts ticker text."""
    symbols = unique_symbols(records)
    return '\n'.join(symbols) + ('\n' if symbols else '')


def tradingview_symbol(symbol: str) -> str:
    # Yahoo names class shares with a dash; TradingView uses a period.
    return re.sub(r'-([A-Z])$', r'.\1', symbol)


def tradingview_txt(records: Iterable[Mapping],
                    exchange_map: Mapping[str, str | None] | None = None,
                    unknown_override: str | None = None) -> tuple[str, list[str]]:
    """TradingView expects comma-separated EXCHANGE:SYMBOL in a .txt file.

    Do not invent exchange prefixes. A missing/unknown venue is omitted unless
    the user explicitly supplies an override or a verified per-symbol mapping.
    """
    rows = list(records)
    exchange_map = exchange_map or {}
    prefixed, unresolved, seen = [], [], set()
    override = EXCHANGE_TO_TV.get(str(unknown_override or '').upper())
    for row in rows:
        sym = clean_symbol(row.get('ticker'))
        if not sym or sym in seen: continue
        seen.add(sym)
        value = exchange_map.get(sym) or row.get('exchange')
        exchange = EXCHANGE_TO_TV.get(str(value or '').upper().strip()) or override
        if not exchange:
            unresolved.append(sym)
        else:
            prefixed.append(f'{exchange}:{tradingview_symbol(sym)}')
    return ','.join(prefixed), unresolved



def tradingview_csv(records: Iterable[Mapping],
                    exchange_map: Mapping[str, str | None] | None = None,
                    unknown_override: str | None = None) -> tuple[bytes, list[str]]:
    """Spreadsheet CSV: one Symbol column with verified TradingView venue prefixes.

    Native TradingView WATCHLIST upload requires .txt, not this .csv. This
    companion download is intended for spreadsheet editing or conversions.
    """
    raw, unresolved = tradingview_txt(records, exchange_map, unknown_override)
    symbols = [value for value in raw.split(',') if value]
    return csv_bytes(({'Symbol': symbol} for symbol in symbols), ['Symbol']), unresolved


def _filename_part(value: object) -> str:
    """Portable human-readable filename segment; no directory separators."""
    import unicodedata
    raw = unicodedata.normalize('NFKD', str(value or ''))
    raw = raw.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^A-Za-z0-9]+', '_', raw).strip('_')[:54] or 'Lista'


def export_filename(*, preset: str, timeframe: str, stage: str, asof: str,
                    platform: str, extension: str,
                    selected_patterns: Iterable[str] = (),
                    selected_statuses: Iterable[str] = (),
                    sctr_floor: float | None = None,
                    rs_floor: float | None = None,
                    max_risk: float | None = None,
                    max_age: int | None = None) -> str:
    """Use the strategy from the completed scan, not the currently selected UI preset."""
    preset_names = {
        'Darvas Breakout': 'Darvas_Breakout',
        'Darvas Box': 'Darvas_Breakout',
        'VCP Pre-Breakout': 'VCP_PreBreakout',
        'VCP / Tight Base': 'VCP_PreBreakout',
        'First Pullback EMA 20W': 'First_Pullback_EMA20W',
        'First Pullback to 20W MA': 'First_Pullback_EMA20W',
        'Univers SCTR': 'Univers_SCTR',
        'Darvas': 'Darvas_Breakout',
    }
    patterns = sorted(set(str(x) for x in selected_patterns if x))
    if stage == 'Universul selectat':
        strategy = 'Univers_SCTR'
    elif patterns:
        names = [preset_names.get(n, _filename_part(n)) for n in patterns]
        strategy = '_si_'.join(names) if len(names) <= 2 else 'Strategii_Multiple'
    else:
        cleaned = str(preset or '').removeprefix('★ ').strip()
        strategy = preset_names.get(cleaned, _filename_part(cleaned))
    statuses = sorted(set(_filename_part(x) for x in selected_statuses if x))
    stage_names = {
        'Rezultate finale': 'RezultateFinale',
        'Dupa RS': 'DupaRS',
        'Dupa RS SCTR': 'DupaRS_SCTR',
        'Candidati tehnici': 'CandidatiTehnici',
        'Universul selectat': 'UniversSCTR',
    }
    parts = [strategy, _filename_part(timeframe), stage_names.get(stage, _filename_part(stage))]
    if statuses:
        parts.append('_si_'.join(statuses) if len(statuses) <= 3 else 'StatusuriMultiple')
    def number_token(number):
        return f'{float(number):g}'.replace('-', 'minus').replace('.', 'p')
    if sctr_floor is not None: parts.append('SCTR' + number_token(sctr_floor))
    if rs_floor is not None: parts.append('RS' + number_token(rs_floor))
    if max_risk is not None: parts.append('RiscMax' + number_token(max_risk))
    if max_age is not None: parts.append('VarstaMax' + str(int(max_age)))
    date = re.sub('[^0-9]', '', str(asof)[:10])
    parts.extend([date or 'FaraData', _filename_part(platform)])
    ext = extension.lower().lstrip('.')
    if ext not in ('csv', 'txt'): raise ValueError('Unsupported file extension')
    return '_'.join(parts) + '.' + ext


def parse_exchange_csv(content: bytes) -> dict[str, str]:
    if len(content) > 1_000_000: raise ValueError('Maximum 1 MB pentru mapa burselor')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('latin1')
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames: raise ValueError('CSV gol')
    colmap = {str(key).lower().strip(): key for key in reader.fieldnames}
    symbol_col = next((colmap[n] for n in ('symbol','ticker') if n in colmap), None)
    exch_col = next((colmap[n] for n in ('exchange','exch','venue') if n in colmap), None)
    if not symbol_col or not exch_col: raise ValueError('CSV trebuie să conțină coloanele Symbol și Exchange')
    results = {}
    for row in reader:
        sym = clean_symbol(row.get(symbol_col))
        ex = str(row.get(exch_col) or '').strip().upper()
        if sym and ex in EXCHANGE_TO_TV: results[sym] = ex
    return results
