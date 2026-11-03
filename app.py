"""DARVAS RS SCREENER — Streamlit app for GitHub + Streamlit Community Cloud.
No simulated signals. Free delayed/EOD Yahoo source + optional SCTR and Barchart.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from io import StringIO
import json
import math
import re
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from screener_core import Rules, normalized, find_setup, annotate_percentile, passes_rs
from hover_chart import render_results
from sctr_paste import parse_sctr_paste

st.set_page_config(page_title='DARVAS RS | Breakout Scanner',page_icon='📈',layout='wide',initial_sidebar_state='expanded')

BG='#0b1018'; PANEL='#131b26'; GREEN='#27d09a'; MUTED='#a7b9cd'
STYLE=r"""
<style>
:root{color-scheme:dark;--background-color:#0b1018;--secondary-background-color:#172231;--text-color:#ecf2f8;--primary-color:#27d09a}
html,body,[data-testid="stApp"],[data-testid="stAppViewContainer"],[data-testid="stHeader"],[data-testid="stMain"]{background:#0b1018!important;color:#ecf2f8!important}
[data-testid="stSidebar"],[data-testid="stSidebarContent"]{background:#101a27!important}
[data-testid="stMainBlockContainer"]{max-width:1780px!important;padding-top:1.5rem!important;padding-left:2rem!important;padding-right:2rem!important}
[data-testid="stMetric"]{border:1px solid #2b3a4d;background:#131e2b;border-radius:12px;padding:12px 16px}
[data-testid="stMetricLabel"]{color:#acbfd2!important}
[data-testid="stMetricValue"]{color:#ecf4fc!important;font-weight:750}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input,[data-testid="stSelectbox"] [data-baseweb="select"],[data-testid="stMultiSelect"] [data-baseweb="select"]{background:#17283b!important;color:#e9f4fd!important;border-color:#3e5870!important}
[data-testid="stSelectbox"] [data-baseweb="select"] *,[data-testid="stMultiSelect"] [data-baseweb="select"] *,[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input,[data-testid="stNumberInput"] input *,[role="listbox"] *,[role="option"] *,[data-baseweb="popover"] *,[data-testid="stWidgetLabel"] *,[data-testid="stSelectbox"] label *,[data-testid="stMultiSelect"] label *{color:#e8f2fc!important;-webkit-text-fill-color:#e8f2fc!important;opacity:1!important}
[role="listbox"],[data-baseweb="popover"],[data-baseweb="menu"],[role="option"]{background:#172637!important;color:#eaf4fe!important}
[data-baseweb="tag"]{background:#243c52!important;color:#edf5fd!important}
[data-testid="stExpander"]{border:1px solid #2b4053;border-radius:11px;background:#111c2a}
[data-testid="stForm"]{border:1px solid #344a5e;background:#101a27;border-radius:13px;padding:8px 14px 16px}
section[data-testid="stSidebar"] [data-testid="stMarkdown"] h3{margin-bottom:4px}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:#1bb981!important;color:#061c14!important;border:1px solid #2aefa9!important;font-weight:800}
.stDownloadButton button{background:#1b3144!important;color:#f0f5ff!important;border:1px solid #426078!important}
small,[data-testid="stCaptionContainer"]{color:#a8bad0!important}
[data-testid="stAlert"]{background:#162638!important;color:#e5f2ff!important}
hr{border-color:#304052}
/* Consistent readable controls, including light-client dropdown portals. */
</style>"""
st.markdown(STYLE,unsafe_allow_html=True)

CORE=['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','AMD','PLTR','NFLX','CRM','ORCL','ADBE','AMAT','MU','LRCX','KLAC','PANW','CRWD','FTNT','NOW','ANET','APP','DDOG','SNOW','NET','SHOP','UBER','ABNB','COIN','HOOD','MSTR','SOFI','RKLB','ASTS','IONQ','RGTI','SMCI','ARM','CAVA','HIMS','CELH','DUOL','AXON','LLY','UNH','ISRG','VRTX','GEV','VRT','ETN','PWR','CAT','DE','JPM','GS','V','MA','WMT','COST','HD','BKNG','LIN','NEM','FCX','MP','XOM','CVX','OXY','HES','RCL','CCL','DAL','UAL','BA','RTX','LMT','NOC','NKE','LULU','ELF','SPOT','RDDT','PINS','SNAP','FSLR','ENPH','TSM','ASML','PDD','BABA','NIO','LI','BIDU']

@st.cache_data(ttl=3600,show_spinner=False)
def get_universe(name:str)->list[str]:
    if name=='Starter (growth leaders)': return CORE
    if name in ('Custom list', 'Imported SCTR list'): return []
    url='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies' if name=='S&P 500' else 'https://en.wikipedia.org/wiki/Nasdaq-100'
    try:
        headers={'User-Agent':'Mozilla/5.0 (Research Screener; public reference data)'}
        response=requests.get(url,headers=headers,timeout=15);response.raise_for_status()
        tables=pd.read_html(StringIO(response.text))
        for tab in tables:
            col=next((c for c in tab.columns if str(c).strip().lower() in ('symbol','ticker','ticker symbol')),None)
            if col is not None:
                vals=[str(x).strip().replace('.','-') for x in tab[col].tolist()]
                vals=[x for x in vals if re.fullmatch(r'[A-Z][A-Z0-9-]{0,8}',x)]
                if len(vals)>=70: return list(dict.fromkeys(vals))
    except Exception as ex:
        st.warning(f'Could not load {name} constituents ({type(ex).__name__}). Falling back to starter list; check the displayed universe size.')
    return CORE


def parse_tickers(text:str)->list[str]:
    raw=re.split(r'[,;\n\t ]+',text.upper().strip())
    return list(dict.fromkeys(x.replace('.','-') for x in raw if re.fullmatch(r'[A-Z^][A-Z0-9.\-^]{0,15}',x)))


def _extract(raw:pd.DataFrame,ticker:str)->pd.DataFrame:
    if raw is None or raw.empty: return pd.DataFrame()
    try:
        if isinstance(raw.columns,pd.MultiIndex):
            lev0=[str(x) for x in raw.columns.get_level_values(0)];lev1=[str(x) for x in raw.columns.get_level_values(1)]
            if ticker in lev0: d=raw[ticker]
            elif ticker in lev1: d=raw.xs(ticker,axis=1,level=1)
            else: return pd.DataFrame()
        else: d=raw
        return normalized(d)
    except Exception: return pd.DataFrame()


@st.cache_data(ttl=900,max_entries=24,show_spinner=False)
def download_prices(symbols:tuple[str,...],months:int)->tuple[dict[str,pd.DataFrame],list[str]]:
    data={}; errors=[]
    period='5y' if months>=38 else ('3y' if months>=25 else '2y')
    for start in range(0,len(symbols),32):
        batch=list(symbols[start:start+32])
        try:
            ret=yf.download(tickers=batch,period=period,interval='1d',group_by='ticker',
                auto_adjust=True,threads=True,progress=False,timeout=18,multi_level_index=True)
            for ticker in batch:
                frame=_extract(ret,ticker)
                if len(frame)>=36:data[ticker]=frame
                else:errors.append(ticker)
        except Exception:
            errors+=batch
    return data,errors


def only_completed(df:pd.DataFrame,completed_only:bool)->pd.DataFrame:
    if not completed_only or df.empty:return df
    ny=datetime.now(ZoneInfo('America/New_York'))
    # Regular session normally ends 16:00 ET; 10-minute guard. Half days may
    # need a manual check. Weekly resampling uses the same completed daily bars.
    if df.index[-1].date()==ny.date() and (ny.hour,ny.minute)<(16,10):
        return df.iloc[:-1]
    return df


def normalized_exchange(value:str|None)->str|None:
    if not value:return None
    key=str(value).upper().strip()
    if key in ('NMS','NCM','NGM','NASDAQ','NAS','NQ'):return 'NASDAQ'
    if key in ('NYQ','NYSE','NYE'):return 'NYSE'
    if key in ('ASE','AMEX','AMERICAN'):return 'AMEX'
    if key in ('PCX','ARC','ARCA','NYSE ARCA'):return 'NYSE Arca'
    return key


@st.cache_data(ttl=86400,show_spinner=False)
def fetch_metadata(symbol:str,need_exchange:bool=False)->dict:
    try:
        ticker=yf.Ticker(symbol)
        fi=ticker.fast_info
        cap=fi.get('market_cap')
        cap=float(cap) if cap and pd.notna(cap) else None
        exchange=normalized_exchange(fi.get('exchange'))
        # If an exchange filter is active, resolve unknown exchange from company
        # metadata, and exclude missing data rather than silently bypass it.
        if need_exchange and exchange is None:
            info=ticker.get_info()
            exchange=normalized_exchange(info.get('exchange') or info.get('fullExchangeName'))
            if cap is None and info.get('marketCap'):cap=float(info['marketCap'])
        return dict(cap=cap,exchange=exchange)
    except Exception:return dict(cap=None,exchange=None)


def bulk_meta(symbols:list[str],need_exchange:bool=False)->dict[str,dict]:
    if not symbols:return {}
    out={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(fetch_metadata,s,need_exchange):s for s in symbols}
        for f in as_completed(futures):
            ticker=futures[f]
            try:out[ticker]=f.result()
            except Exception:out[ticker]={'cap':None,'exchange':None}
    return out


def guess_column(df:pd.DataFrame,aliases:set[str])->str|None:
    for name in df.columns:
        key=re.sub(r'[^a-z0-9]','',str(name).lower())
        if key in aliases:return str(name)
    return None


def parse_scores_csv(content:bytes)->tuple[dict[str,dict],str]:
    try:df=pd.read_csv(StringIO(content.decode('utf-8-sig')))
    except UnicodeDecodeError:df=pd.read_csv(StringIO(content.decode('latin1')))
    except Exception as ex:return {},str(ex)
    ticker_col=guess_column(df,{'symbol','ticker','tickersymbol','stock'})
    if ticker_col is None:return {},'No Symbol / Ticker column found'
    aliases={'sctr':{'sctr','sctrrank','stockchartstechnicalrank','sctrscore'},
      'barchart':{'barchart','technicalopinion','barchartopinion','overallopinion','opinion','technicals','overallaveragesignal'},
      'quality':{'quality','qualityscore','qualityrank'},
      'growth':{'growth','growthscore','growthrank'},
      'cap':{'marketcap','marketcapitalization','mktcap'},'sector':{'sector'},'industry':{'industry'}}
    fields={key:guess_column(df,names) for key,names in aliases.items()}
    out={}
    for _,row in df.iterrows():
        ticker=str(row[ticker_col]).strip().upper().replace('.','-')
        if not re.fullmatch(r'[A-Z][A-Z0-9-]{0,12}',ticker):continue
        result={}
        for key,col in fields.items():
            if col is None or pd.isna(row[col]):continue
            if key in ('sector','industry','barchart'):
                result[key]=str(row[col]).strip();continue
            val=str(row[col]).strip().replace(',','').replace('%','').replace('$','')
            try:result[key]=float(val)
            except ValueError:pass
        if 'cap' in result and result['cap']<1_000_000:
            # Some CSVs export 'market cap' in millions; can't safely infer unit.
            result.pop('cap',None)
        out[ticker]=result
    return out,f'{len(out)} symbols imported; detected columns: '+', '.join(k for k,v in fields.items() if v is not None)


@st.cache_data(ttl=3600,show_spinner=False)
def barchart_signals(symbols:tuple[str,...],key:str)->dict[str,str]:
    if not key:return {}
    results={}
    for start in range(0,len(symbols),25):
        batch=symbols[start:start+25]
        try:
            rsp=requests.get('https://ondemand.websol.barchart.com/getSignal.json',
                params={'apikey':key,'symbols':','.join(batch)},timeout=20)
            rsp.raise_for_status();body=rsp.json()
            for item in body.get('results',[]):
                symbol=str(item.get('symbol','')).upper().replace('.','-')
                val=item.get('overallAverageSignal')
                strength=str(item.get('overallAverageStrength','')).lower()
                if val is not None and strength=='strong' and str(val).lower() in ('buy','sell'):
                    val='Strong '+str(val)
                if symbol and val is not None:results[symbol]=str(val)
        except Exception:continue
    return results


def good_barchart(value,kind):
    if kind=='Off':return True
    if value is None:return False
    s=str(value).lower().replace('_',' ').strip()
    if kind=='Buy or Strong Buy':return 'buy' in s and 'sell' not in s
    if kind=='Strong Buy only':return 'strong buy' in s
    return True


def apply_external_filters(row:dict,minimum_quality:float,minimum_growth:float,
    external_on:bool,sctr_on:bool,sctr_min:float,barchart_filter:str)->bool:
    if external_on:
        if row.get('quality') is None or row.get('growth') is None:return False
        if row['quality']<minimum_quality or row['growth']<minimum_growth:return False
    if sctr_on:
        if row.get('sctr') is None or row['sctr']<sctr_min:return False
    if not good_barchart(row.get('barchart'),barchart_filter):return False
    return True


st.markdown('''<div style="display:flex;gap:15px;align-items:center;margin:0 0 5px">
<div style="font-weight:900;letter-spacing:.11em;font-size:12px;color:#26c98d;border:1px solid #267158;border-radius:5px;padding:4px 8px">DARVAS / RS</div>
<div style="font-weight:800;font-size:30px;letter-spacing:-.04em;color:#e8f3fd">Breakout Scanner</div>
</div><div style="color:#aec2d4;margin-bottom:14px">Daily & Weekly consolidation breakouts · SPY / SPX relative strength · native annotated hover charts</div>''',unsafe_allow_html=True)

with st.sidebar:
    st.header('Data & universe')
    st.caption('Public Yahoo Finance OHLCV (adjusted), cached 15 min. NOT guaranteed real-time.')
    universe=st.selectbox('Stock universe',['Starter (growth leaders)','S&P 500','Nasdaq-100','Imported SCTR list','Custom list'])
    ticker_text=st.text_area('Additional / custom tickers',height=105,placeholder='NVDA, PLTR, ANET, VRT, ...')
    max_symbols=st.number_input('Max tickers to scan',min_value=10,max_value=650,value=150,step=25)
    st.divider()
    st.subheader('Scores: StockCharts / Barchart')
    score_upload=st.file_uploader('CSV with SCTR / Barchart / Quality / Growth',type=['csv'],help='Import exported StockCharts scan results or Barchart data; Quality/Growth must come from your own score source.')
    scores={};import_message=''
    if score_upload:
        scores,import_message=parse_scores_csv(score_upload.getvalue())
        st.caption(import_message)
    with st.expander('📋 Paste SCTR Reports — fără CSV', expanded=False):
        st.caption('Pe StockCharts SCTR Reports selectează tabelul (nu un screenshot), Cmd+C, apoi lipește aici cu Cmd+V. Scorurile sunt cele din momentul copierii; nu se actualizează automat.')
        sctr_text=st.text_area('StockCharts SCTR table text',height=145,key='sctr_pasted',placeholder='Symbol\tName\tSector\tIndustry\tSCTR\tChg\tLast\tVolume\tMarket Cap\nIT\tGartner Group, Inc.\tTechnology\tComputer Services\t97.4\t+2.2\t235.26\t1,457,632\t14.448 B')
        pasted, pasted_message=parse_sctr_paste(sctr_text)
        if sctr_text.strip():
            if pasted:
                st.success(pasted_message)
                for ticker, data in pasted.items():
                    scores.setdefault(ticker, {}).update(data)
                st.caption('SCTR lipit are prioritate față de SCTR din CSV pentru tickerele comune. Nu înlocuiește Quality sau Growth.')
                as_csv=pd.DataFrame([{'Ticker':t,'SCTR':v['sctr'],'Sector':v.get('sector',''),'Industry':v.get('industry','')} for t,v in pasted.items()])
                st.download_button('↓ Descarcă SCTR ca CSV',as_csv.to_csv(index=False).encode('utf-8-sig'),file_name='stockcharts_sctr_import.csv',mime='text/csv')
            else:st.warning(pasted_message)
    api_key=st.text_input('Barchart OnDemand API key (optional)',type='password',help='Licensed API access only. This is not a Barchart website password.')
    enable_api=st.checkbox('Fetch Barchart getSignal through licensed API',value=False,disabled=not bool(api_key))
    st.caption('SCTR: CSV sau text copiat manual din StockCharts. Fără API public SCTR și fără actualizare automată.')
    st.divider()
    st.caption('TIP: Hover over a result ticker to see the actual price chart, EMA, box, volume and RS.')

with st.form('scan_settings'):
    st.markdown('### 01 · Screener universe & settings')
    u1,u2,u3,u4,u5=st.columns([1,1,1.1,1.1,1.2])
    with u1:timeframe=st.selectbox('Timeframe',['Weekly','Daily'])
    with u2:direction=st.selectbox('Direction',['Long','Short'])
    with u3:benchmark=st.selectbox('RS benchmark',['SPY','SPX (^GSPC)'])
    with u4:mode=st.selectbox('Scan mode',['Both','Breakout','Near breakout'])
    with u5:lookback=st.selectbox('Signal within last bars',[1,2,3,4,5,6],index=2)
    a1,a2,a3,a4=st.columns([1,1,1,1])
    with a1:minimum_market_cap=st.number_input('Market cap minimum ($B)',min_value=0.0,max_value=10000.0,value=1.0,step=0.5)
    with a2:quality_min=st.number_input('Quality score minimum',min_value=0,max_value=100,value=60)
    with a3:growth_min=st.number_input('Growth score minimum',min_value=0,max_value=100,value=60)
    with a4:fundamentals_on=st.checkbox('Enforce Quality & Growth CSV',value=False,help='Requires both external scores. No invented Financial Wisdom scores.')
    exchange_filter=st.multiselect('Exchange filter (leave blank for all US exchanges)',['NASDAQ','NYSE','AMEX','NYSE Arca'],default=[])

    st.markdown('### 02 · Box entry filters')
    b1,b2,b3,b4=st.columns(4)
    with b1:min_bars=st.number_input('Minimum consolidation bars',min_value=3,max_value=52,value=6)
    with b2:max_bars=st.number_input('Maximum consolidation bars',min_value=3,max_value=80,value=16)
    with b3:max_box=st.number_input('Maximum box range (%)',min_value=1.0,max_value=100.0,value=20.0,step=1.0)
    with b4:stop_pos=st.number_input('Stop inside box from bottom (%)',min_value=0,max_value=100,value=33)
    c1,c2,c3,c4=st.columns(4)
    with c1:max_risk=st.number_input('Maximum stop-loss risk (%)',min_value=1.0,max_value=100.0,value=16.0)
    with c2:breakout_min=st.number_input('Breakout clearance MIN (%)',min_value=0.0,max_value=40.0,value=4.0,step=0.5)
    with c3:breakout_max=st.number_input('Breakout clearance MAX (%)',min_value=0.5,max_value=1000.0,value=1000.0,step=1.0)
    with c4:close_strength=st.number_input('Minimum close strength (%)',min_value=0,max_value=100,value=75)
    d1,d2,d3,d4=st.columns(4)
    with d1:min_volume=st.number_input('Minimum volume increase vs prior bar (%)',min_value=-100.0,max_value=1000.0,value=1.0)
    with d2:entry_buffer=st.number_input('Entry buffer beyond close (%)',min_value=0.0,max_value=10.0,value=0.01,step=0.01,format='%.2f')
    with d3:ema_on=st.checkbox('20 EMA confirmation',value=True)
    with d4:macd_on=st.checkbox('MACD line above signal (Long)',value=True)
    with st.expander('Advanced box detection',expanded=False):
        e1,e2,e3,e4=st.columns(4)
        with e1:touches=st.number_input('Minimum resistance/support touches',min_value=1,max_value=8,value=1)
        with e2:touch_tol=st.number_input('Touch tolerance (%)',min_value=0.1,max_value=10.0,value=2.5,step=0.5)
        with e3:near_distance=st.number_input('Near-box: max distance from boundary (%)',min_value=0.1,max_value=30.0,value=5.0)
        with e4:completed_only=st.checkbox('Completed candles only (default)',value=True)

    st.markdown('### 03 · Relative Strength + external scores')
    f1,f2,f3,f4=st.columns(4)
    with f1:rs_mode=st.selectbox('RS vs benchmark filter',['3M outperform','Off','52w RS high','3M outperform + 52w high'])
    with f2:rs_min=st.number_input('Min RS 3-month outperformance (%)',min_value=-100.0,max_value=1000.0,value=0.0,step=1.0)
    with f3:rs_pctl=st.number_input('Min RS rank percentile in scanned universe',min_value=0,max_value=100,value=0,step=5,help='Calculated among ALL downloaded universe symbols, not a proprietary RS rank.')
    with f4:sctr_min=st.number_input('Min SCTR (StockCharts)',min_value=0,max_value=100,value=70)
    g1,g2,g3=st.columns([1,1,2])
    with g1:sctr_on=st.checkbox('Enforce imported SCTR',value=False)
    with g2:barchart_filter=st.selectbox('Barchart Opinion',['Off','Buy or Strong Buy','Strong Buy only'])
    with g3:st.caption('Quality/Growth/SCTR/Barchart are intentionally blank unless imported or fetched from licensed source. No score is fabricated.')
    submitted=st.form_submit_button('▶ RUN DARVAS SCAN',type='primary',use_container_width=True)

if min_bars>max_bars:
    st.error('Minimum consolidation bars cannot exceed maximum consolidation bars.')
    st.stop()
if breakout_min>breakout_max:
    st.error('Breakout MIN cannot exceed MAX.')
    st.stop()

base=get_universe(universe)
extra=parse_tickers(ticker_text)
tickers=list(dict.fromkeys(([t for t, v in scores.items() if 'sctr' in v] if universe=='Imported SCTR list' else (base if universe!='Custom list' else []))+extra))[:int(max_symbols)]
st.caption(f'Universe selected: **{len(tickers)} symbols** / {(sum('sctr' in v for v in scores.values()) if universe=='Imported SCTR list' else len(base))+len(extra)} requested before deduplication and cap · RS = (stock / benchmark) momentum · 3M = 13 weekly bars / 63 daily bars.')
if submitted:
    if not tickers:
        st.error('Add tickers in the sidebar for a custom scan.');st.stop()
    with st.spinner(f'Downloading daily price histories for {len(tickers)} stocks, then evaluating {timeframe.lower()} Darvas setups...'):
        benchmark_ticker='SPY' if benchmark=='SPY' else '^GSPC'
        all_tickers=tuple(dict.fromkeys([*tickers,benchmark_ticker]))
        raw,errors=download_prices(all_tickers,38)
        bench=only_completed(raw.get(benchmark_ticker,pd.DataFrame()),completed_only)
        if len(bench)<80:
            st.error('Benchmark OHLCV could not be retrieved. Scan cancelled — no fabricated results.');st.stop()
        rules=Rules(direction=direction,minimum_bars=int(min_bars),maximum_bars=int(max_bars),
          max_box_pct=max_box,stop_in_box_pct=stop_pos,max_stop_pct=max_risk,
          min_breakout_pct=breakout_min,max_breakout_pct=breakout_max,
          min_close_strength=close_strength,min_volume_increase=min_volume,
          entry_buffer_pct=entry_buffer,confirm_ema=ema_on,confirm_macd=macd_on,
          min_touches=touches,touch_tolerance_pct=touch_tol,recent_bars=int(lookback),
          near_distance_pct=near_distance,mode=mode)
        candidates=[];rs_all={};available=0
        for ticker in tickers:
            d=only_completed(raw.get(ticker,pd.DataFrame()),completed_only)
            if d.empty:continue
            available+=1
            setup,rs=find_setup(d,bench,timeframe,rules)
            rs_all[ticker]=rs.get('rs_3m')
            if setup:candidates.append({'ticker':ticker,**setup})
        percentiles=annotate_percentile(rs_all)
        selected=[];rejected_rs=0;rejected_scores=0
        api_signals=barchart_signals(tuple(s['ticker'] for s in candidates),api_key) if enable_api else {}
        # Apply external/rank checks before potentially costly market-cap verification.
        for r in candidates:
            t=r['ticker'];r['rs_percentile']=percentiles.get(t)
            values=scores.get(t,{})
            for field in ('quality','growth','sctr','barchart','sector','industry'):
                r[field]=values.get(field)
            if r.get('barchart') is None and t in api_signals:r['barchart']=api_signals[t]
            if not passes_rs(r,rs_mode,rs_min,r['rs_percentile'],rs_pctl):
                rejected_rs+=1;continue
            if not apply_external_filters(r,quality_min,growth_min,fundamentals_on,sctr_on,sctr_min,barchart_filter):
                rejected_scores+=1;continue
            selected.append(r)
        cap_unavailable=0;cap_under=0;exchange_rejected=0
        if selected and (minimum_market_cap>0 or exchange_filter):
            needed=[r['ticker'] for r in selected if
                    (minimum_market_cap>0 and scores.get(r['ticker'],{}).get('cap') is None)
                    or bool(exchange_filter)]
            meta=bulk_meta(needed,need_exchange=bool(exchange_filter))
            qualified=[]
            for r in selected:
                cap=scores.get(r['ticker'],{}).get('cap')
                if cap is None:cap=meta.get(r['ticker'],{}).get('cap')
                r['cap_billion']=round(cap/1e9,2) if cap else None
                r['exchange']=normalized_exchange(meta.get(r['ticker'],{}).get('exchange'))
                if minimum_market_cap>0:
                    if cap is None:cap_unavailable+=1;continue
                    if cap < minimum_market_cap*1e9:cap_under+=1;continue
                if exchange_filter and r['exchange'] not in exchange_filter:
                    exchange_rejected+=1;continue
                qualified.append(r)
            selected=qualified
        else:
            for r in selected:
                cap=scores.get(r['ticker'],{}).get('cap')
                r['cap_billion']=round(cap/1e9,2) if cap else None
                r['exchange']=None
        selected.sort(key=lambda r:(r['status']=='BREAKOUT',r.get('rs_percentile') or -100,r.get('rs_3m') or -100),reverse=True)
        st.session_state['results']={'data':selected,'timeframe':timeframe,'benchmark':benchmark,
           'asof':datetime.now(ZoneInfo('Europe/Bucharest')).strftime('%Y-%m-%d %H:%M Europe/Bucharest'),
           'requested':len(tickers),'available':available,'technical':len(candidates),
           'rejected_rs':rejected_rs,'rejected_scores':rejected_scores,
           'missing':len(tickers)-available,'cap_unavailable':cap_unavailable,'cap_under':cap_under,'exchange_rejected':exchange_rejected,
           'mode':mode,'score_info':import_message,'mincap':minimum_market_cap}

if 'results' in st.session_state:
    res=st.session_state['results']; rows=res['data']
    st.divider(); st.markdown('### 04 · Scan results')
    k1,k2,k3,k4,k5=st.columns(5)
    k1.metric('Matches',len(rows));k2.metric('Breakout',sum(r['status']=='BREAKOUT' for r in rows))
    k3.metric('Near box',sum(r['status']=='NEAR BOX' for r in rows))
    k4.metric('Technical candidates',res['technical']);k5.metric('OHLCV available',f"{res['available']}/{res['requested']}")
    st.caption('Last scan: '+res['asof']+' · Data: Yahoo Finance adjusted historical prices (EOD/delayed) · Hover on ticker for price+volume+RS chart. No alerts/orders placed.')
    if res['missing']:st.warning(f"{res['missing']} symbols had insufficient/unavailable price history and were NOT scanned.")
    if res['cap_unavailable']:
        st.warning(f"Market cap unavailable for {res['cap_unavailable']} candidates; excluded because the ${res['mincap']}B minimum is active. Set cap minimum to 0 to keep them without verification.")
    if not rows:
        st.info('No signals match all active filters. Try **Both**, reduce 4% breakout clearance, set RS to Off, broaden the universe, or disable unavailable external-score filters. These are authentic zero results, not sample tickers.')
    if rows:
        st.iframe(render_results(rows,res['timeframe'],res['benchmark']),height=750,width='stretch')
        flat=[]
        for r in rows:
            flat.append({k:v for k,v in r.items() if k not in ('chart','rs_line','rs_dates')})
        st.download_button('↓ Download matched tickers & scan metrics (CSV)',pd.DataFrame(flat).to_csv(index=False).encode('utf-8-sig'),
          file_name=f"darvas_rs_{res['timeframe'].lower()}_{datetime.now().strftime('%Y%m%d')}.csv",mime='text/csv')
    with st.expander('Scan diagnostics & methodology'):
        st.write(f"Technical setups before RS/scores/cap: **{res['technical']}**. RS rejected **{res['rejected_rs']}**; external scores rejected **{res['rejected_scores']}**; cap below minimum **{res['cap_under']}**; cap unavailable **{res['cap_unavailable']}**; exchange rejected/unknown **{res['exchange_rejected']}**.")
        st.markdown('**Box range** = (highest high − lowest low) / lowest low across preceding N bars. **Breakout** = completed candle close at least X% above resistance; its candle is excluded from the box. **Close strength** = (close − low) / (high − low) on breakout candle. **Volume** = change vs immediately prior bar. **Initial stop** = box bottom + 33% × box height (long); **risk** uses entry beyond breakout close. **RS 3M** = return of (stock close / benchmark close) ratio over 13 weekly or 63 daily bars. **RS rank** = percentile within downloaded universe (not proprietary SCTR).')
        st.caption('Historical 412% return reported in the video is NOT reproduced by this app; this is a current screener, not a point-in-time survivorship-free portfolio backtest. Free public sources can be delayed, incomplete, adjusted or rate-limited. Market-cap filters use current caps, not historical caps.')
else:
    st.info('Choose your universe and filters, then click **RUN DARVAS SCAN**. No synthetic or prefilled scan results are shown.')

st.markdown('''<div style="border-top:1px solid #273b4b;margin-top:18px;padding-top:12px;color:#8398ad;font-size:12px">DARVAS RS • Technical research dashboard • Not investment advice • Does not place orders • SCTR/Barchart/Fundamental scores require authorized external data</div>''',unsafe_allow_html=True)
