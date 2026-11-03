"""Pure Darvas price/volume logic. Uses *completed* OHLCV bars only.

Prices use adjusted OHLC supplied by caller. No data retrieval here, so this
module can be tested independently of Yahoo Finance and Streamlit.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import math
import numpy as np
import pandas as pd

REQUIRED = ('Open', 'High', 'Low', 'Close', 'Volume')

@dataclass(frozen=True)
class Rules:
    direction: str = 'Long'
    minimum_bars: int = 6
    maximum_bars: int = 16
    max_box_pct: float = 20.0
    stop_in_box_pct: float = 33.0
    max_stop_pct: float = 16.0
    min_breakout_pct: float = 4.0
    max_breakout_pct: float = 1000.0
    min_close_strength: float = 75.0
    min_volume_increase: float = 1.0
    entry_buffer_pct: float = 0.01
    ema_period: int = 20
    confirm_ema: bool = True
    confirm_macd: bool = True
    min_touches: int = 1
    touch_tolerance_pct: float = 2.5
    recent_bars: int = 3
    near_distance_pct: float = 5.0
    mode: str = 'Both'  # 'Breakout', 'Near breakout', 'Both'


def normalized(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty or not set(REQUIRED).issubset(data.columns):
        return pd.DataFrame(columns=list(REQUIRED))
    df = data.loc[:, list(REQUIRED)].copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.apply(pd.to_numeric, errors='coerce').dropna(subset=list(REQUIRED))
    df = df[(df.Open > 0) & (df.High >= df.Low) & (df.Low > 0) & (df.Close > 0)]
    return df.sort_index()[~df.index.duplicated(keep='last')]


def to_period(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    df = normalized(df)
    if timeframe == 'Weekly' and not df.empty:
        df = df.resample('W-FRI', label='right', closed='right').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
    return df


def indicators(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    d = df.copy()
    d['EMA'] = d.Close.ewm(span=period, adjust=False, min_periods=period).mean()
    ema12 = d.Close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = d.Close.ewm(span=26, adjust=False, min_periods=26).mean()
    d['MACD'] = ema12 - ema26
    d['MACD_signal'] = d.MACD.ewm(span=9, adjust=False, min_periods=9).mean()
    return d


def rs_features(stock: pd.DataFrame, benchmark: pd.DataFrame, timeframe: str) -> Dict:
    if stock.empty or benchmark.empty:
        return dict(rs_3m=None, rs_1m=None, rs_new_high=None, rs_line=[], rs_dates=[])
    bench = benchmark.Close.reindex(stock.index).ffill(limit=1)
    ratio = (stock.Close / bench.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    ratio = ratio.dropna()
    if len(ratio) < 2:
        return dict(rs_3m=None, rs_1m=None, rs_new_high=None, rs_line=[], rs_dates=[])
    p3 = 13 if timeframe == 'Weekly' else 63
    p1 = 4 if timeframe == 'Weekly' else 21
    lookback = 52 if timeframe == 'Weekly' else 252
    def momentum(n):
        return float(100 * (ratio.iloc[-1] / ratio.iloc[-1-n] - 1)) if len(ratio) > n else None
    rh = bool(ratio.iloc[-1] >= ratio.iloc[-min(len(ratio),lookback):].max() * (1-1e-10))
    recent = ratio.iloc[-min(110, len(ratio)):]
    base = float(recent.iloc[0])
    vals = [round(float(v/base*100), 3) for v in recent]
    return dict(rs_3m=momentum(p3),rs_1m=momentum(p1),rs_new_high=rh,
                rs_line=vals,rs_dates=[x.strftime('%Y-%m-%d') for x in recent.index])


def _touches(box: pd.DataFrame, upper: float, lower: float, tol_pct: float, direction: str) -> int:
    tol = tol_pct/100
    return int((box.High >= upper*(1-tol)).sum() if direction=='Long'
               else (box.Low <= lower*(1+tol)).sum())


def _score_close_strength(candle: pd.Series, direction: str) -> float:
    rng = float(candle.High - candle.Low)
    if rng <= 0:
        return 0
    return 100 * float((candle.Close-candle.Low)/rng if direction=='Long' else (candle.High-candle.Close)/rng)


def _event_result(d: pd.DataFrame, idx: int, rules: Rules) -> Optional[Dict]:
    """Find best valid breakout box immediately preceding bar idx; no look-ahead."""
    curr, prev = d.iloc[idx], d.iloc[idx-1]
    best = None
    for n in range(rules.minimum_bars, min(rules.maximum_bars, idx)+1):
        box = d.iloc[idx-n:idx]
        hi = float(box.High.max()); lo = float(box.Low.min())
        box_pct = 100*(hi-lo)/lo
        if box_pct > rules.max_box_pct or hi <= lo:
            continue
        touches = _touches(box,hi,lo,rules.touch_tolerance_pct,rules.direction)
        if touches < rules.min_touches:
            continue
        breakout_pct = (100*(float(curr.Close)/hi-1) if rules.direction=='Long'
                        else 100*(lo/float(curr.Close)-1))
        if not (rules.min_breakout_pct <= breakout_pct <= rules.max_breakout_pct):
            continue
        strength = _score_close_strength(curr,rules.direction)
        vol_pct = 100*(float(curr.Volume)/max(float(prev.Volume),1)-1)
        if strength < rules.min_close_strength or vol_pct < rules.min_volume_increase:
            continue
        if rules.confirm_ema and (pd.isna(curr.EMA) or
              (curr.Close <= curr.EMA if rules.direction=='Long' else curr.Close >= curr.EMA)):
            continue
        # In the original video's interface: MACD line ABOVE signal (not MACD > 0).
        if rules.confirm_macd and (pd.isna(curr.MACD_signal) or
              (curr.MACD <= curr.MACD_signal if rules.direction=='Long' else curr.MACD >= curr.MACD_signal)):
            continue
        enter = float(curr.Close)*(1+rules.entry_buffer_pct/100 if rules.direction=='Long'
                                    else 1-rules.entry_buffer_pct/100)
        stop = lo+(hi-lo)*rules.stop_in_box_pct/100 if rules.direction=='Long' else hi-(hi-lo)*rules.stop_in_box_pct/100
        risk_pct = 100*(enter-stop)/enter if rules.direction=='Long' else 100*(stop-enter)/enter
        if risk_pct <= 0 or risk_pct > rules.max_stop_pct:
            continue
        candidate = dict(status='BREAKOUT', signal_date=str(d.index[idx].date()),
            bars=n,box_top=hi,box_bottom=lo,box_pct=box_pct,stop=stop,
            risk_pct=risk_pct,entry=enter,close=float(curr.Close),
            clearance=breakout_pct,close_strength=strength,volume_change=vol_pct,
            touches=touches,ema20=float(curr.EMA) if pd.notna(curr.EMA) else None,
            macd_diff=float(curr.MACD-curr.MACD_signal) if pd.notna(curr.MACD_signal) else None,
            distance_pct=breakout_pct)
        if best is None or (candidate['bars'],candidate['touches']) > (best['bars'],best['touches']):
            best=candidate
    return best


def _near_result(d: pd.DataFrame, rules: Rules) -> Optional[Dict]:
    idx=len(d)-1; curr=d.iloc[idx]
    best=None
    for n in range(rules.minimum_bars, min(rules.maximum_bars, len(d))+1):
        box=d.iloc[len(d)-n:]
        hi=float(box.High.max()); lo=float(box.Low.min())
        pct=100*(hi-lo)/lo
        if pct > rules.max_box_pct or hi<=lo:
            continue
        touch=_touches(box,hi,lo,rules.touch_tolerance_pct,rules.direction)
        if touch<rules.min_touches: continue
        if rules.direction=='Long':
            distance=100*(hi/float(curr.Close)-1)
            if not 0<=distance<=rules.near_distance_pct: continue
        else:
            distance=100*(float(curr.Close)/lo-1)
            if not 0<=distance<=rules.near_distance_pct: continue
        if rules.confirm_ema and (pd.isna(curr.EMA) or
             (curr.Close <= curr.EMA if rules.direction=='Long' else curr.Close >= curr.EMA)):
            continue
        if rules.confirm_macd and (pd.isna(curr.MACD_signal) or
             (curr.MACD <= curr.MACD_signal if rules.direction=='Long' else curr.MACD >= curr.MACD_signal)):
            continue
        # Stop and prospective entry at top + buffer, not current close.
        enter=(hi*(1+rules.entry_buffer_pct/100) if rules.direction=='Long'
                else lo*(1-rules.entry_buffer_pct/100))
        stop=lo+(hi-lo)*rules.stop_in_box_pct/100 if rules.direction=='Long' else hi-(hi-lo)*rules.stop_in_box_pct/100
        risk_pct=100*(enter-stop)/enter if rules.direction=='Long' else 100*(stop-enter)/enter
        if risk_pct<=0 or risk_pct>rules.max_stop_pct: continue
        result=dict(status='NEAR BOX',signal_date=str(d.index[-1].date()),bars=n,
            box_top=hi,box_bottom=lo,box_pct=pct,stop=stop,risk_pct=risk_pct,
            entry=enter,close=float(curr.Close),clearance=None,close_strength=None,
            volume_change=None,touches=touch,ema20=float(curr.EMA) if pd.notna(curr.EMA) else None,
            macd_diff=float(curr.MACD-curr.MACD_signal) if pd.notna(curr.MACD_signal) else None,
            distance_pct=distance)
        if best is None or (result['bars'],result['touches'])>(best['bars'],best['touches']): best=result
    return best


def find_setup(bars: pd.DataFrame, bench: pd.DataFrame, timeframe: str, rules: Rules) -> tuple[Optional[Dict], Dict]:
    d=indicators(to_period(bars,timeframe),rules.ema_period)
    b=to_period(bench,timeframe)
    rs=rs_features(d,b,timeframe)
    if len(d)<max(35, rules.minimum_bars+2):
        return None,rs
    event=None
    if rules.mode in ('Breakout','Both'):
        for idx in range(len(d)-1,max(rules.minimum_bars+1,len(d)-rules.recent_bars-1),-1):
            event=_event_result(d,idx,rules)
            if event: break
    if event is None and rules.mode in ('Near breakout','Both'):
        event=_near_result(d,rules)
    if event is not None:
        event.update(rs)
        # Values for hover chart with MA overlay and candlesticks.
        end=min(len(d),160)
        subset=d.iloc[-end:].copy()
        event['chart']=[{
          'd':k.strftime('%Y-%m-%d'),'o':round(float(r.Open),4),
          'h':round(float(r.High),4),'l':round(float(r.Low),4),
          'c':round(float(r.Close),4),'v':int(r.Volume),
          'ema':round(float(r.EMA),4) if pd.notna(r.EMA) else None
        } for k,r in subset.iterrows()]
    return event,rs


def annotate_percentile(scores: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    valid={k:v for k,v in scores.items() if v is not None and math.isfinite(v)}
    if not valid: return {k:None for k in scores}
    vals=pd.Series(valid,dtype=float).rank(method='average',pct=True)*100
    return {k:round(float(vals[k]),1) if k in vals else None for k in scores}


def passes_rs(rs: Dict,mode:str,min_rs:float,percentile:Optional[float],minimum_percentile:float)->bool:
    if mode=='Off': return True
    if mode in ('3M outperform','3M outperform + 52w high'):
        if rs.get('rs_3m') is None or rs['rs_3m']<min_rs: return False
    if mode in ('52w RS high','3M outperform + 52w high') and not rs.get('rs_new_high'):
        return False
    if minimum_percentile>0 and (percentile is None or percentile<minimum_percentile):
        return False
    return True
