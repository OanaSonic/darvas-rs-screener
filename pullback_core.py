"""Rule-based FIRST pullback to the 20-week moving average.

All calculations use completed weekly bars, with no data retrieval or forward look.
This is a scanner heuristic, not a model trained to label discretionary setups.
"""
from __future__ import annotations

ENGINE_API_VERSION = 'v6.1'

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
from screener_core import to_period, rs_features, indicators


@dataclass(frozen=True)
class PullbackRules:
    ma_kind: str = 'EMA'  # EMA or SMA, applied to weekly closes
    ma_period: int = 20
    breakout_lookback: int = 8
    breakout_clearance_pct: float = 0.5
    max_prebreakout_range_pct: float = 35.0
    min_advance_weeks: int = 3
    max_weeks_since_breakout: int = 16
    min_advance_pct: float = 8.0
    touch_tolerance_pct: float = 2.0  # low can be slightly ABOVE MA
    max_undercut_pct: float = 2.5  # reject large penetrations below MA
    watch_distance_pct: float = 5.0
    close_below_ma_pct: float = 0.5
    ma_rise_weeks: int = 3
    stop_buffer_pct: float = 0.5
    max_risk_pct: float = 16.0
    entry_buffer_pct: float = 0.1
    max_signal_age: int = 3
    stage_mode: str = 'All'  # All, Watch, First touch, Bounce


def _append_chart(res:dict,d:pd.DataFrame,b:pd.DataFrame) -> dict:
    rs=rs_features(d,b,'Weekly')
    res.update(rs)
    res['signal_age_bars']=len(d)-1-res['signal_idx']
    res['current_close']=float(d.Close.iloc[-1])
    entry=res.get('entry')
    res['extension_from_entry_pct']=(100*(res['current_close']/entry-1) if entry is not None and entry>0 else None)
    subset=d.iloc[-160:]
    res['chart']=[{'d':k.strftime('%Y-%m-%d'), 'o':round(float(r.Open),4),
                   'h':round(float(r.High),4),'l':round(float(r.Low),4),
                   'c':round(float(r.Close),4),'v':int(r.Volume),
                   'ema':round(float(r.MA20),4) if pd.notna(r.MA20) else None}
                  for k,r in subset.iterrows()]
    res['ma_kind']=res['ma_kind']+' 20W'
    res['breakout_date']=str(d.index[res['breakout_idx']].date())
    if res.get('touch_idx') is not None:
        res['touch_date']=str(d.index[res['touch_idx']].date())
    else:
        res['touch_date']=None
    res['box_top']=None;res['box_bottom']=None;res['box_pct']=None
    res['bars']=None;res['box_start_date']=None;res['box_end_date']=None
    res['distance_pct']=res.get('ma_distance_pct')
    res['contraction_ratio']=None;res['atr_ratio']=None;res['volume_ratio']=None
    res['earlier_pivot']=None;res['major_base_top']=None
    res['resistance_basis']=None
    res['close']=float(d.Close.iloc[res['signal_idx']])
    res['ema20']=float(d.MA20.iloc[res['signal_idx']])
    res['signal_date']=str(d.index[res['signal_idx']].date())
    res['pattern']='First pullback 20W MA'
    res['direction']='Long'
    res.pop('signal_idx',None);res.pop('breakout_idx',None);res.pop('touch_idx',None)
    return res


def _base_breakout(d:pd.DataFrame, i:int, rules:PullbackRules) -> Optional[dict]:
    n=rules.breakout_lookback
    if i<n+1 or pd.isna(d.MA20.iloc[i]):return None
    prev=d.iloc[i-n:i]
    hi=float(prev.High.max());lo=float(prev.Low.min())
    if lo<=0 or 100*(hi/lo-1)>rules.max_prebreakout_range_pct:return None
    candle=d.iloc[i]
    if (candle.Close <= candle.MA20 or
        candle.Close < hi*(1+rules.breakout_clearance_pct/100)):
        return None
    return {'breakout_idx':i,'breakout_level':hi,'breakout_close':float(candle.Close),
            'base_width_pct':100*(hi/lo-1)}


def _valid_impulse(d:pd.DataFrame,b:dict,touch_idx:int,rules:PullbackRules) -> Optional[float]:
    i=b['breakout_idx']
    if touch_idx-i-1<rules.min_advance_weeks:return None
    prior=d.iloc[i+1:touch_idx]
    if prior.empty:return None
    # A touch of EMA before target week means it is NOT the first pullback.
    ma=prior.MA20.to_numpy(dtype=float)
    if not np.isfinite(ma).all():return None
    lows=prior.Low.to_numpy(dtype=float)
    if np.any(lows<=ma*(1+rules.touch_tolerance_pct/100)):
        return None
    # Post-breakout price must first run higher for several weekly candles.
    peak=max(float(d.High.iloc[i]),float(prior.High.max()))
    advance=100*(peak/b['breakout_close']-1)
    if advance<rules.min_advance_pct:return None
    return advance


def first_pullback_setup(bars:pd.DataFrame,benchmark:pd.DataFrame,timeframe:str,
                         rules:PullbackRules)->tuple[Optional[dict],dict]:
    """Find recent first weekly MA touch / near-touch / bounce after an older breakout.

    Do not call this on Daily. Breakout must precede the signal by >= min_advance_weeks;
    intermediate weekly lows must not have already touched the MA tolerance band.
    A WATCH is only a prospect, not a filled entry or triggered signal.
    """
    if timeframe!='Weekly':
        raise ValueError('First pullback to 20W MA is defined on Weekly bars only.')
    d=to_period(bars,'Weekly')
    b=to_period(benchmark,'Weekly')
    if len(d)<max(45,rules.ma_period+rules.breakout_lookback+rules.min_advance_weeks+3):
        return None,rs_features(d,b,'Weekly')
    d=indicators(d,20)
    d['MA20']=(d.Close.rolling(rules.ma_period,min_periods=rules.ma_period).mean()
               if rules.ma_kind=='SMA' else d.Close.ewm(span=rules.ma_period,adjust=False,min_periods=rules.ma_period).mean())
    rs=rs_features(d,b,'Weekly')
    last=len(d)-1
    results=[]
    earliest=max(rules.ma_period+rules.breakout_lookback,last-rules.max_weeks_since_breakout-rules.max_signal_age-2)
    # Consider ONLY recent touch/bounce weeks. Watch is always the last completed week.
    for touch_idx in range(max(earliest,last-rules.max_signal_age-2),last+1):
        candle=d.iloc[touch_idx]
        ma=float(candle.MA20)
        if not np.isfinite(ma) or ma<=0:continue
        if touch_idx-rules.ma_rise_weeks<0 or ma<=d.MA20.iloc[touch_idx-rules.ma_rise_weeks]:continue
        low=float(candle.Low)
        close=float(candle.Close)
        low_vs_ma=100*(low/ma-1)
        is_touch=(-rules.max_undercut_pct<=low_vs_ma<=rules.touch_tolerance_pct and
                   close>=ma*(1-rules.close_below_ma_pct/100))
        is_near=(rules.touch_tolerance_pct<low_vs_ma<=rules.watch_distance_pct and
                 touch_idx==last and close>=ma)
        if not is_touch and not is_near:continue
        for breakout_idx in range(max(rules.ma_period+rules.breakout_lookback,
                                      touch_idx-rules.max_weeks_since_breakout),
                                  touch_idx-rules.min_advance_weeks+1):
            breakout=_base_breakout(d,breakout_idx,rules)
            if breakout is None:continue
            advance=_valid_impulse(d,breakout,touch_idx,rules)
            if advance is None:continue
            if is_near:
                if rules.stage_mode not in ('All','Watch'):continue
                status='PULLBACK WATCH';signal_idx=touch_idx
                entry=None;stop=None;risk=None
            else:
                # A confirmed bounce must occur AFTER the first touch, within 1–2 weeks.
                bounce_idx=next((j for j in range(touch_idx+1,min(last+1,touch_idx+3))
                    if d.Close.iloc[j]>d.High.iloc[touch_idx]*(1+rules.entry_buffer_pct/100)
                    and d.Close.iloc[j]>d.MA20.iloc[j]
                    and d.Low.iloc[touch_idx+1:j+1].min()>=ma*(1-rules.max_undercut_pct/100)),None)
                if bounce_idx is not None:
                    status='BOUNCE CONFIRMED';signal_idx=bounce_idx
                else:
                    status='FIRST MA TOUCH';signal_idx=touch_idx
                    if touch_idx!=last:continue  # stale touches not mistaken for fresh triggers
                if rules.stage_mode == 'Watch' or (rules.stage_mode=='Bounce' and status!='BOUNCE CONFIRMED') or (rules.stage_mode=='First touch' and status!='FIRST MA TOUCH'):
                    continue
                entry=float(d.High.iloc[touch_idx])*(1+rules.entry_buffer_pct/100)
                stop=float(d.Low.iloc[touch_idx])*(1-rules.stop_buffer_pct/100)
                risk=100*(entry-stop)/entry
                if risk<=0 or risk>rules.max_risk_pct:continue
            if last-signal_idx>=rules.max_signal_age:continue
            res={**breakout,'status':status,'signal_idx':signal_idx,'touch_idx':touch_idx,
                 'ma_kind':rules.ma_kind,'ma20':ma,'ma_distance_pct':100*(close/ma-1),
                 'distance_to_ma_low_pct':low_vs_ma,'weeks_after_breakout':touch_idx-breakout_idx,
                 'advance_pct':advance,'entry':entry,'stop':stop,'risk_pct':risk,
                 'close_strength':None,'volume_change':None}
            results.append(res)
    if not results:return None,rs
    # Favor recent confirmed bounce, then a first touch, then near-watch;
    # when duplicate anchor candidates exist, prefer the earliest breakout.
    priority={'BOUNCE CONFIRMED':3,'FIRST MA TOUCH':2,'PULLBACK WATCH':1}
    chosen=max(results,key=lambda r:(r['signal_idx'],priority[r['status']],-r['breakout_idx']))
    return _append_chart(chosen,d,b),rs
