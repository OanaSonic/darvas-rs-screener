"""Pure Darvas price/volume logic. Uses *completed* OHLCV bars only.

Prices use adjusted OHLC supplied by caller. No data retrieval here, so this
module can be tested independently of Yahoo Finance and Streamlit.
"""
from __future__ import annotations

ENGINE_API_VERSION = 'v6.1'

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
    mode: str = 'Both'  # 'Breakout', 'Near breakout', 'Both', 'All setups'
    resistance_basis: str = 'Wick high'  # or 'Highest close' (early-warning, non-classic)
    require_confirmed_pivot: bool = False
    max_inside_distance_pct: float = 20.0
    earlier_pivot_lookback: int = 52
    pattern_family: str = 'Both' # 'Darvas', 'VCP', 'Both'
    vcp_max_tight_pct: float = 12.0
    vcp_max_range_ratio: float = 0.80 # newest range <= 80% older range
    vcp_max_atr_ratio: float = 0.95 # latest average bar range smaller than earlier
    vcp_require_dry_volume: bool = False
    vcp_max_volume_ratio: float = 0.90
    vcp_breakout_min_pct: float = 0.15 # distinct from 4% Darvas confirmation
    vcp_stop_buffer_pct: float = 0.30 # below final contraction low



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


def _box_boundaries(box: pd.DataFrame, rules: Rules) -> tuple[float,float]:
    """Wick-extreme is the standard mechanical range; highest close is exploratory."""
    if rules.resistance_basis == 'Highest close':
        return float(box.Close.max()), float(box.Close.min())
    return float(box.High.max()), float(box.Low.min())


def _confirmed_top_or_bottom(box: pd.DataFrame, hi: float, lo: float, rules: Rules) -> bool:
    """A pivot must be followed by 3 STRICTLY lower highs (or higher lows)."""
    if not rules.require_confirmed_pivot:
        return True
    if rules.resistance_basis != 'Wick high':
        return False  # close-only tops are not classical high-pivots
    if len(box) < 4:
        return False
    if rules.direction == 'Long':
        h=box.High.to_numpy(dtype=float)
        return any(abs(h[i]-hi)<max(1e-7,hi*1e-8) and all(x<hi for x in h[i+1:i+4])
                   for i in range(len(h)-3))
    lows=box.Low.to_numpy(dtype=float)
    return any(abs(lows[i]-lo)<max(1e-7,lo*1e-8) and all(x>lo for x in lows[i+1:i+4])
               for i in range(len(lows)-3))


def earlier_pivot(d:pd.DataFrame, event_idx:int, box_start:int, box_top:float,
                  rules:Rules) -> Optional[float]:
    """Informational PRIOR swing-high reference, NOT a Darvas box entry trigger.

    Only prior confirmed pivot highs: 2 earlier and 3 later LOWER highs.
    This can lie below a later wick and may already have been broken.
    """
    if rules.direction!='Long' or box_start<6:
        return None
    first=max(2,box_start-rules.earlier_pivot_lookback)
    h=d.High.to_numpy(dtype=float)
    pivots=[]
    for i in range(first,box_start):
        if i+3>=event_idx:break
        if all(h[i]>h[j] for j in (i-1,i-2,i+1,i+2,i+3)):
            if 0.75*box_top<h[i]<box_top*0.995:
                pivots.append(float(h[i]))
    return round(max(pivots),4) if pivots else None


def _vcp_contraction(d: pd.DataFrame, idx: int, n: int, rules: Rules) -> Optional[Dict]:
    """Mechanical 2-stage contraction proxy, NOT discretionary Minervini VCP.

    Earlier (n bars) compared with more recent (n bars) preceding signal bar.
    Latest candle is excluded from pivot to avoid self-referencing and look-ahead.
    Only the final tight-box highs/lows define the VCP pivot and stop basis.
    """
    if idx < 2*n:
        return None
    early=d.iloc[idx-2*n:idx-n];tight=d.iloc[idx-n:idx]
    hi=float(tight.High.max());lo=float(tight.Low.min())
    if hi<=lo or lo<=0:
        return None
    tight_pct=100*(hi-lo)/lo
    early_low=float(early.Low.min())
    early_range=100*(float(early.High.max())-early_low)/early_low
    if early_range<=0 or tight_pct>rules.vcp_max_tight_pct or tight_pct>rules.max_box_pct:
        return None
    range_ratio=tight_pct/early_range
    if range_ratio>rules.vcp_max_range_ratio:
        return None
    # Mean intrabar true range as percentage of price (simple robust proxy).
    def mean_true_range(frame):
        previous=frame.Close.shift(1).fillna(frame.Open)
        tr=np.maximum.reduce(((frame.High-frame.Low).to_numpy(),
                   abs(frame.High-previous).to_numpy(),abs(frame.Low-previous).to_numpy()))
        return float(np.mean(tr/frame.Close.to_numpy()))
    early_atr=mean_true_range(early)
    tight_atr=mean_true_range(tight)
    atr_ratio=tight_atr/early_atr if early_atr>0 else float('inf')
    if atr_ratio>rules.vcp_max_atr_ratio:
        return None
    early_vol=float(early.Volume.mean());tight_vol=float(tight.Volume.mean())
    volume_ratio=tight_vol/early_vol if early_vol>0 else float('inf')
    if rules.vcp_require_dry_volume and volume_ratio>rules.vcp_max_volume_ratio:
        return None
    if _touches(tight,hi,lo,rules.touch_tolerance_pct,'Long')<rules.min_touches:
        return None
    return dict(box_top=hi,box_bottom=lo,box_pct=tight_pct,bars=n,
         box_start_idx=idx-n,box_end_idx=idx-1,
         major_base_top=float(early.High.max()),early_range_pct=early_range,
         contraction_ratio=range_ratio,atr_ratio=atr_ratio,
         volume_ratio=volume_ratio,volume_dryup_pct=100*(1-volume_ratio),
         touches=_touches(tight,hi,lo,rules.touch_tolerance_pct,'Long'),
         pattern='VCP / tight base')


def _vcp_candidate(d:pd.DataFrame, idx:int, rules:Rules, breakout:bool)->Optional[Dict]:
    """Screen a pre-breakout VCP or a close above the final tight pivot."""
    if rules.direction!='Long':return None
    curr=d.iloc[idx]
    best=None;best_score=float('-inf')
    min_n=max(4,rules.minimum_bars)
    for n in range(min_n,min(rules.maximum_bars,idx//2)+1):
        q=_vcp_contraction(d,idx,n,rules)
        if q is None:continue
        hi=q['box_top'];lo=q['box_bottom'];close=float(curr.Close)
        if breakout:
            clear=100*(close/hi-1)
            if not rules.vcp_breakout_min_pct<=clear<=rules.max_breakout_pct:continue
            strength=_score_close_strength(curr,'Long')
            volpct=100*(float(curr.Volume)/max(float(d.iloc[idx-1].Volume),1)-1)
            if strength<rules.min_close_strength or volpct<rules.min_volume_increase:continue
            status='BREAKOUT'
        else:
            if not (lo<=close<=hi):continue
            clear=None;volpct=None;strength=None
            gap=100*(hi/close-1)
            maxgap=rules.max_inside_distance_pct if rules.mode=='All setups' else rules.near_distance_pct
            if gap>maxgap:continue
            status='PRE-BREAKOUT' if gap<=rules.near_distance_pct else 'IN BOX'
        if rules.confirm_ema and (pd.isna(curr.EMA) or close<=curr.EMA):continue
        if rules.confirm_macd and (pd.isna(curr.MACD_signal) or curr.MACD<=curr.MACD_signal):continue
        entry=(close if breakout else hi)*(1+rules.entry_buffer_pct/100)
        stop=lo*(1-rules.vcp_stop_buffer_pct/100)
        risk=100*(entry-stop)/entry
        if risk<=0 or risk>rules.max_stop_pct:continue
        gap=clear if breakout else 100*(hi/close-1)
        event=dict(q, status=status,signal_date=str(d.index[idx].date()),entry=entry,
              close=close,stop=stop,risk_pct=risk,clearance=clear,
              distance_pct=gap,close_strength=strength,volume_change=volpct,
              ema20=float(curr.EMA) if pd.notna(curr.EMA) else None,
              macd_diff=float(curr.MACD-curr.MACD_signal) if pd.notna(curr.MACD_signal) else None,
              signal_idx=idx)
        # Prefer a compact, still-contracted final base near its pivot.
        quality=(1-q['contraction_ratio'])*2 + (1-min(q['atr_ratio'],2)) + max(0,1-q['volume_ratio'])*.2 - (n*.001)
        if quality>best_score:best=event;best_score=quality
    return best


def _event_result(d: pd.DataFrame, idx: int, rules: Rules) -> Optional[Dict]:
    """Find best valid breakout box immediately preceding bar idx; no look-ahead."""
    curr, prev = d.iloc[idx], d.iloc[idx-1]
    best = None
    for n in range(rules.minimum_bars, min(rules.maximum_bars, idx)+1):
        box = d.iloc[idx-n:idx]
        hi, lo = _box_boundaries(box,rules)
        if not _confirmed_top_or_bottom(box,hi,lo,rules): continue
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
        candidate = dict(pattern='Darvas',status='BREAKOUT', signal_date=str(d.index[idx].date()),
            bars=n,box_top=hi,box_bottom=lo,box_pct=box_pct,stop=stop,
            risk_pct=risk_pct,entry=enter,close=float(curr.Close),
            clearance=breakout_pct,close_strength=strength,volume_change=vol_pct,
            touches=touches,ema20=float(curr.EMA) if pd.notna(curr.EMA) else None,
            macd_diff=float(curr.MACD-curr.MACD_signal) if pd.notna(curr.MACD_signal) else None,
            distance_pct=breakout_pct, box_start_idx=idx-n, box_end_idx=idx-1,signal_idx=idx)
        if best is None or (candidate['bars'],candidate['touches']) > (best['bars'],best['touches']):
            best=candidate
    return best


def _near_result(d: pd.DataFrame, rules: Rules) -> Optional[Dict]:
    idx=len(d)-1; curr=d.iloc[idx]
    best=None
    for n in range(rules.minimum_bars, min(rules.maximum_bars, len(d))+1):
        box=d.iloc[len(d)-n:]
        hi,lo=_box_boundaries(box,rules)
        if not _confirmed_top_or_bottom(box,hi,lo,rules): continue
        pct=100*(hi-lo)/lo
        if pct > rules.max_box_pct or hi<=lo:
            continue
        touch=_touches(box,hi,lo,rules.touch_tolerance_pct,rules.direction)
        if touch<rules.min_touches: continue
        if rules.direction=='Long':
            distance=100*(hi/float(curr.Close)-1)
            if not 0<=distance<=max(rules.near_distance_pct,rules.max_inside_distance_pct if rules.mode=='All setups' else 0): continue
        else:
            distance=100*(float(curr.Close)/lo-1)
            if not 0<=distance<=max(rules.near_distance_pct,rules.max_inside_distance_pct if rules.mode=='All setups' else 0): continue
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
        if float(curr.Close)<lo or float(curr.Close)>hi:continue
        status=('PRE-BREAKOUT' if distance<=rules.near_distance_pct else 'IN BOX')
        result=dict(pattern='Darvas',status=status,signal_date=str(d.index[-1].date()),bars=n,
            box_top=hi,box_bottom=lo,box_pct=pct,stop=stop,risk_pct=risk_pct,
            entry=enter,close=float(curr.Close),clearance=None,close_strength=None,
            volume_change=None,touches=touch,ema20=float(curr.EMA) if pd.notna(curr.EMA) else None,
            macd_diff=float(curr.MACD-curr.MACD_signal) if pd.notna(curr.MACD_signal) else None,
            distance_pct=distance,box_start_idx=len(d)-n,box_end_idx=len(d)-1,signal_idx=len(d)-1)
        if best is None or (result['bars'],result['touches'])>(best['bars'],best['touches']): best=result
    return best


def find_setup(bars: pd.DataFrame, bench: pd.DataFrame, timeframe: str, rules: Rules) -> tuple[Optional[Dict], Dict]:
    d=indicators(to_period(bars,timeframe),rules.ema_period)
    b=to_period(bench,timeframe)
    rs=rs_features(d,b,timeframe)
    if len(d)<max(35, rules.minimum_bars+2):
        return None,rs
    event=None
    # Consider all real breakout signals within the requested age window.
    breakout_options=[]
    if rules.mode in ('Breakout','Both','All setups'):
        for idx in range(len(d)-1,max(rules.minimum_bars+1,len(d)-rules.recent_bars-1),-1):
            if rules.pattern_family in ('Darvas','Both'):
                candidate=_event_result(d,idx,rules)
                if candidate:breakout_options.append(candidate)
            if rules.pattern_family in ('VCP','Both') and rules.direction=='Long':
                candidate=_vcp_candidate(d,idx,rules,True)
                if candidate:breakout_options.append(candidate)
        if breakout_options:
            # Most recent first; at identical date prefer VCP (tighter risk defined).
            event=max(breakout_options,key=lambda r:(r['signal_idx'],r.get('pattern')!='Darvas'))
    if event is None and rules.mode in ('Near breakout','Both','All setups'):
        if rules.pattern_family in ('VCP','Both') and rules.direction=='Long':
            event=_vcp_candidate(d,len(d)-1,rules,False)
        if event is None and rules.pattern_family in ('Darvas','Both'):
            event=_near_result(d,rules)
    if event is not None:
        event.update(rs)
        age=int(len(d)-1-event['signal_idx'])
        event['signal_age_bars']=age
        event['current_close']=float(d.Close.iloc[-1])
        event['extension_from_entry_pct']=(100*(event['current_close']/event['entry']-1)
                if rules.direction=='Long' else 100*(event['entry']/event['current_close']-1))
        event['earlier_pivot']=(earlier_pivot(d,event['signal_idx'],event['box_start_idx'],event['box_top'],rules)
                               if event.get('pattern')=='Darvas' else None)
        event['box_start_date']=str(d.index[event['box_start_idx']].date())
        event['box_end_date']=str(d.index[event['box_end_idx']].date())
        event['resistance_basis']=rules.resistance_basis
        event.pop('box_end_idx',None)
        event.pop('box_start_idx',None)
        event.pop('signal_idx',None)
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
