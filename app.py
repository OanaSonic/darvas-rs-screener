"""DARVAS RS SCREENER — Streamlit app for GitHub + Streamlit Community Cloud.
No simulated signals. Free delayed/EOD Yahoo source + optional imported StockCharts SCTR.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from io import StringIO
import re
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

import screener_core as screener_engine
import pullback_core as pullback_engine
from screener_core import Rules, normalized, find_setup, annotate_percentile, passes_rs
from pullback_core import PullbackRules, first_pullback_setup
from hover_chart import render_results
from sctr_paste import parse_sctr_paste

st.set_page_config(page_title='DARVAS RS | Quick Presets & Weekly Pullback',page_icon='📈',layout='wide',initial_sidebar_state='expanded')

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


def only_completed(df:pd.DataFrame,completed_only:bool,timeframe:str='Daily')->pd.DataFrame:
    if not completed_only or df.empty:return df
    ny=datetime.now(ZoneInfo('America/New_York'))
    if timeframe=='Weekly':
        # Weekly resample would otherwise mistake a Mon–Thu PARTIAL WEEK for a closed candle.
        last_friday=ny.date()-timedelta(days=(ny.weekday()-4)%7)
        if ny.weekday()==4 and (ny.hour,ny.minute)<(16,10):
            last_friday-=timedelta(days=7)
        return df.loc[df.index.date<=last_friday]
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
def fetch_exchange(symbol:str)->str|None:
    """Only called when exchange filter is selected; no market-cap queries."""
    try:
        t=yf.Ticker(symbol)
        exchange=normalized_exchange(t.fast_info.get('exchange'))
        if not exchange:
            info=t.get_info()
            exchange=normalized_exchange(info.get('exchange') or info.get('fullExchangeName'))
        return exchange
    except Exception:
        return None


def bulk_exchanges(symbols:list[str])->dict[str,str|None]:
    if not symbols:return {}
    output={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(fetch_exchange,s):s for s in symbols}
        for f in as_completed(futures):
            ticker=futures[f]
            try:output[ticker]=f.result()
            except Exception:output[ticker]=None
    return output


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
      'sector':{'sector'},'industry':{'industry'}}
    fields={key:guess_column(df,names) for key,names in aliases.items()}
    out={}
    for _,row in df.iterrows():
        ticker=str(row[ticker_col]).strip().upper().replace('.','-')
        if not re.fullmatch(r'[A-Z][A-Z0-9-]{0,12}',ticker):continue
        result={}
        for key,col in fields.items():
            if col is None or pd.isna(row[col]):continue
            if key in ('sector','industry'):
                result[key]=str(row[col]).strip();continue
            val=str(row[col]).strip().replace(',','').replace('%','').replace('$','')
            try:result[key]=float(val)
            except ValueError:pass
        out[ticker]=result
    return out,f'{len(out)} symbols imported; detected columns: '+', '.join(k for k,v in fields.items() if v is not None)


st.markdown('''<div style="display:flex;gap:15px;align-items:center;margin:0 0 5px">
<div style="font-weight:900;letter-spacing:.11em;font-size:12px;color:#26c98d;border:1px solid #267158;border-radius:5px;padding:4px 8px">DARVAS / RS</div>
<div style="font-weight:800;font-size:30px;letter-spacing:-.04em;color:#e8f3fd">Breakout Scanner</div>
</div><div style="color:#aec2d4;margin-bottom:14px">Darvas Breakout · VCP Pre-Breakout · First Pullback EMA 20W · RS vs SPY/SPX · hover charts</div>''',unsafe_allow_html=True)

with st.sidebar:
    st.header('Data & universe')
    st.caption('Public Yahoo Finance OHLCV (adjusted), cached 15 min. NOT guaranteed real-time.')
    universe=st.selectbox('Stock universe',['Starter (growth leaders)','S&P 500','Nasdaq-100','Imported SCTR list','Custom list'])
    ticker_text=st.text_area('Additional / custom tickers',height=105,placeholder='NVDA, PLTR, ANET, VRT, ...')
    max_symbols=st.number_input('Max tickers to scan',min_value=10,max_value=650,value=500,step=25)
    st.divider()
    st.subheader('StockCharts · SCTR')
    score_upload=st.file_uploader('CSV with ticker + SCTR (optional sector / industry)',type=['csv'],help='Optional CSV exported from StockCharts. Alternatively paste the public SCTR table below.')
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
                st.caption('Scorurile SCTR lipite au prioritate față de CSV (snapshot manual, fără actualizare automată).')
                as_csv=pd.DataFrame([{'Ticker':t,'SCTR':v['sctr'],'Sector':v.get('sector',''),'Industry':v.get('industry','')} for t,v in pasted.items()])
                st.download_button('↓ Descarcă SCTR ca CSV',as_csv.to_csv(index=False).encode('utf-8-sig'),file_name='stockcharts_sctr_import.csv',mime='text/csv')
            else:st.warning(pasted_message)
    st.caption('SCTR este un snapshot din StockCharts; nu reprezintă date live. Poți relipi tabelul când vrei să îl actualizezi.')
    st.divider()
    st.caption('TIP: Hover over a result ticker to see the actual price chart, EMA, box, volume and RS.')


# Presets are selected OUTSIDE the form, so the chosen strategy is visible and
# a change immediately rebuilds the settings with that preset's defaults.
PRESETS = {
    'Darvas Breakout': {
        'timeframe':'Weekly','strategy':'Darvas + VCP','pattern_family':'Darvas',
        'mode':'Breakout','lookback':3,'breakout_min':4.0,'close_strength':75,
        'min_volume':1.0,'ema_on':True,'macd_on':True,
    },
    'VCP Pre-Breakout': {
        'timeframe':'Weekly','strategy':'Darvas + VCP','pattern_family':'VCP',
        'mode':'Near breakout','lookback':3,'breakout_min':4.0,
        'close_strength':60,'min_volume':0.0,'ema_on':True,'macd_on':False,
    },
    'First Pullback EMA 20W': {
        'timeframe':'Weekly','strategy':'First Pullback to 20W MA','pattern_family':'Both',
        'mode':'Both','lookback':3,'breakout_min':4.0,'close_strength':75,
        'min_volume':1.0,'ema_on':True,'macd_on':True,
    },
}

st.markdown('### Quick strategy presets')
preset_name=st.selectbox('Choose your setup',list(PRESETS),
    help='A preset gives recommended starting parameters, not a validated trading signal. Open Advanced Filters to customize.')
preset=PRESETS[preset_name]
if st.session_state.get('_active_scan_preset') != preset_name:
    st.session_state.pop('results', None)  # Do not show results from a different preset.
    st.session_state['_active_scan_preset'] = preset_name
st.caption({
    'Darvas Breakout': 'Completed weekly/daily close above the high of the prior box; classic breakout confirmation.',
    'VCP Pre-Breakout': 'Late tight consolidation after a wider range; search before the local pivot is broken.',
    'First Pullback EMA 20W': 'Weekly only: breakout, several weeks of advance, and first return toward the rising 20-week EMA.',
}[preset_name])

with st.form('scan_settings_'+preset_name.replace(' ','_')):
    st.markdown('### 01 · Quick filters')
    q1,q2,q3,q4=st.columns(4)
    with q1:
        timeframe=st.selectbox('Chart timeframe', ['Weekly'] if preset_name=='First Pullback EMA 20W' else ['Weekly','Daily'],
            index=0, help='The first pullback strategy is always WEEKLY.')
    with q2:benchmark=st.selectbox('RS benchmark',['SPY','SPX (^GSPC)'])
    with q3:lookback=st.selectbox('Signal freshness · completed bars',[1,2,3,5,10,20],index=2,
        help='A breakout/bounce must have occurred within the last N completed candles.')
    with q4:sctr_min=st.number_input('Min SCTR (StockCharts)',min_value=0,max_value=100,value=70)
    q5,q6=st.columns([1.9,1.1])
    with q5:rs_mode=st.selectbox('Relative Strength filter',
        ['3M outperform','Off','52w RS high','3M outperform + 52w high'],
        help='3M outperformance uses the stock/benchmark ratio, not absolute stock return.')
    with q6:sctr_on=st.checkbox('Require imported SCTR',value=(universe=='Imported SCTR list'),
        help='Stocks without imported SCTR are excluded when enabled.')
    st.caption('All other criteria are configured for the selected strategy. Expand only if you need to customize them.')

    with st.expander('⚙ Advanced Filters — optional',expanded=False):
        st.markdown('#### Universe, pattern & signal filters')
        x1,x2,x3=st.columns(3)
        with x1:
            direction=st.selectbox('Direction',['Long','Short'] if preset_name=='Darvas Breakout' else ['Long'])
        with x2:
            mode_options=['Both (Breakout + Pre-Breakout)','Breakout only','Pre-Breakout only','All incl. Inside Box']
            default_label={'Breakout':'Breakout only','Near breakout':'Pre-Breakout only',
                'Both':'Both (Breakout + Pre-Breakout)','All setups':'All incl. Inside Box'}[preset['mode']]
            mode_label=st.selectbox('Signal type',mode_options,index=mode_options.index(default_label))
        with x3:
            families=['Darvas Box only','Tight Base / VCP only','Both (Darvas + Tight VCP)']
            family_label={'Darvas':'Darvas Box only','VCP':'Tight Base / VCP only',
                'Both':'Both (Darvas + Tight VCP)'}[preset['pattern_family']]
            family_choice=st.selectbox('Pattern family',families,index=families.index(family_label),
                disabled=preset_name=='First Pullback EMA 20W',
                help='For the pullback strategy, the initial breakout is detected by the pullback engine.')
        mode={'Both (Breakout + Pre-Breakout)':'Both','Breakout only':'Breakout',
              'Pre-Breakout only':'Near breakout','All incl. Inside Box':'All setups'}[mode_label]
        pattern_family={'Darvas Box only':'Darvas','Tight Base / VCP only':'VCP',
                        'Both (Darvas + Tight VCP)':'Both'}[family_choice]
        strategy=preset['strategy']
        exchange_filter=st.multiselect('Exchange filter (empty = no exchange lookup)',
            ['NASDAQ','NYSE','AMEX','NYSE Arca'],default=[])
        if direction=='Short' and pattern_family in ('VCP','Both'):
            st.caption('Short signals are evaluated by Darvas only. The VCP model detects long setups.')

        st.markdown('#### Darvas Box · breakout confirmation')
        b1,b2,b3,b4=st.columns(4)
        with b1:min_bars=st.number_input('Minimum consolidation bars',min_value=3,max_value=52,value=6)
        with b2:max_bars=st.number_input('Maximum consolidation bars',min_value=3,max_value=80,value=16)
        with b3:max_box=st.number_input('Maximum box range (%)',min_value=1.0,max_value=100.0,value=20.0,step=1.0)
        with b4:stop_pos=st.number_input('Stop inside box from bottom (%)',min_value=0,max_value=100,value=33)
        c1,c2,c3,c4=st.columns(4)
        with c1:max_risk=st.number_input('Maximum stop-loss risk (%)',min_value=1.0,max_value=100.0,value=16.0)
        with c2:breakout_min=st.number_input('Darvas breakout clearance MIN (%)',min_value=0.0,max_value=40.0,value=preset['breakout_min'],step=0.5)
        with c3:breakout_max=st.number_input('Breakout clearance MAX (%)',min_value=0.5,max_value=1000.0,value=1000.0,step=1.0)
        with c4:close_strength=st.number_input('Minimum close strength (%)',min_value=0,max_value=100,value=preset['close_strength'])
        d1,d2,d3,d4=st.columns(4)
        with d1:min_volume=st.number_input('Minimum volume increase vs prior bar (%)',min_value=-100.0,max_value=1000.0,value=preset['min_volume'])
        with d2:entry_buffer=st.number_input('Entry buffer beyond close (%)',min_value=0.0,max_value=10.0,value=0.01,step=0.01,format='%.2f')
        with d3:ema_on=st.checkbox('20 EMA confirmation',value=preset['ema_on'])
        with d4:macd_on=st.checkbox('MACD above signal (long)',value=preset['macd_on'])
        e1,e2,e3,e4=st.columns(4)
        with e1:touches=st.number_input('Minimum resistance/support touches',min_value=1,max_value=8,value=1)
        with e2:touch_tol=st.number_input('Touch tolerance (%)',min_value=0.1,max_value=10.0,value=2.5,step=0.5)
        with e3:near_distance=st.number_input('Pre-Breakout: max distance (%)',min_value=0.1,max_value=30.0,value=5.0)
        with e4:max_inside_distance=st.number_input('Inside box: max gap (%)',min_value=5.0,max_value=100.0,value=20.0)
        e5,e6,e7=st.columns([2,1.7,1.6])
        with e5:resistance_basis=st.selectbox('Darvas resistance method',
            ['Highest wick (range box)','Highest close (early-warning, non-classic)'],index=0)
        with e6:confirmed_pivot=st.checkbox('Require 3 lower highs after pivot',value=False)
        with e7:completed_only=st.checkbox('Completed candles only',value=True)

        st.markdown('#### Tight Base / VCP · last contraction')
        st.caption('Late N-bar range compared with the previous N bars; local pivot = high of FINAL contraction.')
        v1,v2,v3,v4=st.columns(4)
        with v1:vcp_tight=st.number_input('VCP max final box width (%)',min_value=1.0,max_value=40.0,value=12.0,step=1.0)
        with v2:vcp_range=st.number_input('Latest / earlier range max ratio',min_value=0.1,max_value=1.0,value=0.8,step=0.05)
        with v3:vcp_atr=st.number_input('Latest / earlier avg TR max ratio',min_value=0.1,max_value=1.5,value=0.95,step=0.05)
        with v4:vcp_clear=st.number_input('VCP breakout above pivot MIN (%)',min_value=0.0,max_value=10.0,value=0.15,step=0.05)
        v5,v6,v7=st.columns(3)
        with v5:vcp_dry=st.checkbox('Require VCP volume dry-up',value=False)
        with v6:vcp_vol=st.number_input('Max latest / earlier volume ratio',min_value=0.1,max_value=2.0,value=0.9,step=0.05)
        with v7:vcp_stop=st.number_input('VCP stop buffer below base low (%)',min_value=0.0,max_value=5.0,value=0.3,step=0.1)

        st.markdown('#### First Pullback · Weekly 20 MA')
        st.caption('Only active for First Pullback EMA 20W preset. WATCH is not a confirmed entry.')
        pb1,pb2,pb3,pb4=st.columns(4)
        with pb1:pb_ma=st.selectbox('20-week moving average',['EMA','SMA'])
        with pb2:pb_stage=st.selectbox('Pullback stage',['All','Watch','First touch','Bounce'])
        with pb3:pb_upweeks=st.number_input('Weeks of uptrend after breakout MIN',min_value=2,max_value=10,value=3)
        with pb4:pb_maxweeks=st.number_input('Max weeks since breakout',min_value=4,max_value=36,value=16)
        pb5,pb6,pb7,pb8=st.columns(4)
        with pb5:pb_advance=st.number_input('Impulse gain above breakout MIN (%)',min_value=2.0,max_value=100.0,value=8.0,step=1.0)
        with pb6:pb_touch=st.number_input('First MA touch tolerance (%)',min_value=0.0,max_value=10.0,value=2.0,step=0.5)
        with pb7:pb_watch=st.number_input('Watch: low above MA max gap (%)',min_value=2.0,max_value=20.0,value=5.0,step=0.5)
        with pb8:pb_undercut=st.number_input('Max low undercut below MA (%)',min_value=0.0,max_value=12.0,value=2.5,step=0.5)
        pb9,pb10,pb11,pb12=st.columns(4)
        with pb9:pb_breakperiod=st.number_input('Pre-breakout highest-high window (weeks)',min_value=4,max_value=20,value=8)
        with pb10:pb_breakclear=st.number_input('Prior breakout close above high (%)',min_value=0.0,max_value=10.0,value=0.5,step=0.25)
        with pb11:pb_stop=st.number_input('Stop below touch-week low (%)',min_value=0.0,max_value=10.0,value=0.5,step=0.25)
        with pb12:pb_risk=st.number_input('Pullback maximum entry risk (%)',min_value=1.0,max_value=40.0,value=16.0,step=1.0)

        st.markdown('#### Additional RS thresholds')
        f1,f2=st.columns(2)
        with f1:rs_min=st.number_input('Min 3M outperformance vs benchmark (%)',min_value=-100.0,max_value=1000.0,value=0.0,step=1.0)
        with f2:rs_pctl=st.number_input('Min RS rank percentile in scanned universe',min_value=0,max_value=100,value=0,step=5)

    submitted=st.form_submit_button('▶ RUN SCREENER',type='primary',use_container_width=True)
if pb_watch<pb_touch and timeframe=='Weekly':
    st.error('Pullback WATCH max gap must be >= first MA touch tolerance.');st.stop()
if pb_maxweeks<=pb_upweeks and timeframe=='Weekly':
    st.error('Pullback breakout max age must be greater than required uptrend weeks.');st.stop()
if min_bars>max_bars:
    st.error('Minimum consolidation bars cannot exceed maximum consolidation bars.')
    st.stop()
if confirmed_pivot and resistance_basis.startswith('Highest close'):
    st.error('Confirmed pivot (3 lower highs) requires Highest wick resistance method.');st.stop()
if breakout_min>breakout_max:
    st.error('Breakout MIN cannot exceed MAX.')
    st.stop()

base=get_universe(universe)
extra=parse_tickers(ticker_text)
tickers=list(dict.fromkeys(([t for t, v in scores.items() if 'sctr' in v] if universe=='Imported SCTR list' else (base if universe!='Custom list' else []))+extra))[:int(max_symbols)]
st.caption(f'Universe selected: **{len(tickers)} symbols** / {(sum('sctr' in v for v in scores.values()) if universe=='Imported SCTR list' else len(base))+len(extra)} requested before deduplication and scan limit · RS = (stock / benchmark) momentum · 3M = 13 weekly bars / 63 daily bars.')
if submitted:
    required_engine_version='v6.1'
    installed_core=getattr(screener_engine,'ENGINE_API_VERSION','older/unknown')
    installed_pullback=getattr(pullback_engine,'ENGINE_API_VERSION','older/unknown')
    if installed_core!=required_engine_version or installed_pullback!=required_engine_version:
        st.error('Version mismatch between app.py and screening modules. Upload ALL v6 files from the ZIP (not only app.py): screener_core.py and pullback_core.py must also be v6.1.')
        st.code(f'app.py requires {required_engine_version}; screener_core.py={installed_core}; pullback_core.py={installed_pullback}')
        st.stop()
    if not tickers:
        st.error('Add tickers in the sidebar for a custom scan.');st.stop()
    with st.spinner(f'Downloading daily price histories for {len(tickers)} stocks, then evaluating {timeframe.lower()} breakout/pullback setups...'):
        benchmark_ticker='SPY' if benchmark=='SPY' else '^GSPC'
        all_tickers=tuple(dict.fromkeys([*tickers,benchmark_ticker]))
        raw,errors=download_prices(all_tickers,38)
        bench=only_completed(raw.get(benchmark_ticker,pd.DataFrame()),completed_only,timeframe)
        if len(bench)<80:
            st.error('Benchmark OHLCV could not be retrieved. Scan cancelled — no fabricated results.');st.stop()
        try:
            rules=Rules(direction=direction,minimum_bars=int(min_bars),maximum_bars=int(max_bars),
          max_box_pct=max_box,stop_in_box_pct=stop_pos,max_stop_pct=max_risk,
          min_breakout_pct=breakout_min,max_breakout_pct=breakout_max,
          min_close_strength=close_strength,min_volume_increase=min_volume,
          entry_buffer_pct=entry_buffer,confirm_ema=ema_on,confirm_macd=macd_on,
          min_touches=touches,touch_tolerance_pct=touch_tol,recent_bars=int(lookback),
          near_distance_pct=near_distance,max_inside_distance_pct=max_inside_distance,mode=mode,
          resistance_basis='Highest close' if resistance_basis.startswith('Highest close') else 'Wick high',
          require_confirmed_pivot=confirmed_pivot, pattern_family=pattern_family,
          vcp_max_tight_pct=vcp_tight, vcp_max_range_ratio=vcp_range,
          vcp_max_atr_ratio=vcp_atr, vcp_require_dry_volume=vcp_dry,
          vcp_max_volume_ratio=vcp_vol, vcp_breakout_min_pct=vcp_clear,
          vcp_stop_buffer_pct=vcp_stop)
            pullback_rules=PullbackRules(ma_kind=pb_ma,breakout_lookback=int(pb_breakperiod),
            breakout_clearance_pct=pb_breakclear,min_advance_weeks=int(pb_upweeks),
            max_weeks_since_breakout=int(pb_maxweeks),min_advance_pct=pb_advance,
            touch_tolerance_pct=pb_touch,max_undercut_pct=pb_undercut,
            watch_distance_pct=pb_watch,stop_buffer_pct=pb_stop,max_risk_pct=pb_risk,
            max_signal_age=int(lookback),stage_mode=pb_stage)
        except TypeError as exc:
            st.error('Incompatible engine parameters. Replace app.py, screener_core.py AND pullback_core.py together from the same v6 archive.')
            st.code(f'{type(exc).__name__}: {exc}')
            st.stop()
        candidates=[];rs_all={};available=0
        for ticker in tickers:
            d=only_completed(raw.get(ticker,pd.DataFrame()),completed_only,timeframe)
            if d.empty:continue
            available+=1
            if strategy!='First Pullback to 20W MA':
                setup,rs=find_setup(d,bench,timeframe,rules)
                if setup:candidates.append({'ticker':ticker,**setup})
            else:
                rs={}
            if timeframe=='Weekly' and strategy!='Darvas + VCP':
                pullback, pb_rs=first_pullback_setup(d,bench,'Weekly',pullback_rules)
                if pullback:candidates.append({'ticker':ticker,**pullback})
                rs=pb_rs
            rs_all[ticker]=rs.get('rs_3m')
        percentiles=annotate_percentile(rs_all)
        selected=[];rejected_rs=0;rejected_scores=0
        for r in candidates:
            t=r['ticker'];r['rs_percentile']=percentiles.get(t)
            values=scores.get(t,{})
            for field in ('sctr','sector','industry'):
                r[field]=values.get(field)
            if not passes_rs(r,rs_mode,rs_min,r['rs_percentile'],rs_pctl):
                rejected_rs+=1;continue
            if sctr_on and (r.get('sctr') is None or r['sctr']<sctr_min):
                rejected_scores+=1;continue
            selected.append(r)
        # No market-cap requirements, no automatic cap metadata lookups.
        # Only verify exchange when the user explicitly selected an exchange filter.
        exchange_rejected=0
        if exchange_filter and selected:
            exchanges=bulk_exchanges([r['ticker'] for r in selected])
            accepted=[]
            for r in selected:
                r['exchange']=exchanges.get(r['ticker'])
                if r['exchange'] not in exchange_filter:
                    exchange_rejected+=1
                    continue
                accepted.append(r)
            selected=accepted
        else:
            for r in selected:
                r['exchange']=None
        priority={'BOUNCE CONFIRMED':5,'FIRST MA TOUCH':4,'BREAKOUT':3,'PRE-BREAKOUT':2,'PULLBACK WATCH':1,'IN BOX':0}
        selected.sort(key=lambda r:(priority.get(r['status'],0),r.get('rs_percentile') or -100,r.get('rs_3m') or -100),reverse=True)
        st.session_state['results']={'data':selected,'timeframe':timeframe,'benchmark':benchmark,
           'asof':datetime.now(ZoneInfo('Europe/Bucharest')).strftime('%Y-%m-%d %H:%M Europe/Bucharest'),
           'requested':len(tickers),'available':available,'technical':len(candidates),
           'rejected_rs':rejected_rs,'rejected_scores':rejected_scores,
           'missing':len(tickers)-available,'exchange_rejected':exchange_rejected,
           'mode':mode,'strategy':strategy,'score_info':import_message,
           'technical_candidates':sorted(candidates,key=lambda r:r.get('rs_3m') or -100,reverse=True)[:120],
           'resistance_basis':rules.resistance_basis,'confirmed_pivot':confirmed_pivot,'lookback':lookback}

if 'results' in st.session_state:
    res=st.session_state['results']; rows=res['data']
    st.divider(); st.markdown('### 04 · Scan results')
    k1,k2,k3,k4,k5,k6=st.columns(6)
    k1.metric('Matches',len(rows));k2.metric('Darvas/VCP Breakout',sum(r['status']=='BREAKOUT' for r in rows))
    k3.metric('Pre-Breakout',sum(r['status']=='PRE-BREAKOUT' for r in rows))
    k4.metric('First 20W MA Pullback',sum(r['pattern']=='First pullback 20W MA' for r in rows))
    k5.metric('Technical candidates',res['technical']);k6.metric('OHLCV available',f"{res['available']}/{res['requested']}")
    st.caption('Last scan: '+res['asof']+' · Data: Yahoo Finance adjusted historical prices (EOD/delayed) · Hover on ticker for price+volume+RS chart. No alerts/orders placed.')
    if res['missing']:st.warning(f"{res['missing']} symbols had insufficient/unavailable price history and were NOT scanned.")
    if not rows:
        st.info('No signals match all active filters. Try a broader stage selection, increase the pullback watch tolerance, set RS to Off, widen the VCP range tolerance, or disable the SCTR requirement for a diagnostic scan. These are authentic zero results, not sample tickers.')
    if rows:
        st.iframe(render_results(rows,res['timeframe'],res['benchmark']),height=750,width='stretch')
        flat=[]
        for r in rows:
            flat.append({k:v for k,v in r.items() if k not in ('chart','rs_line','rs_dates')})
        st.download_button('↓ Download matched tickers & scan metrics (CSV)',pd.DataFrame(flat).to_csv(index=False).encode('utf-8-sig'),
          file_name=f"darvas_rs_pullback_{res['timeframe'].lower()}_{datetime.now().strftime('%Y%m%d')}.csv",mime='text/csv')
    if res.get('technical_candidates'):
        with st.expander(f"Technical candidate explorer ({res['technical']} setups before RS/SCTR/exchange) · top 120",expanded=False):
            st.caption('Research list BEFORE RS, SCTR or exchange filters. Not actionable signals until verified. Hover/click ticker for the chart.')
            st.iframe(render_results(res['technical_candidates'],res['timeframe'],res['benchmark']),height=560,width='stretch')
            subset=[{k:v for k,v in r.items() if k not in ('chart','rs_line','rs_dates')} for r in res['technical_candidates']]
            st.download_button('↓ Export technical candidates CSV',pd.DataFrame(subset).to_csv(index=False).encode('utf-8-sig'),file_name='darvas_candidates.csv',mime='text/csv')
    with st.expander('Scan diagnostics & methodology'):
        st.write(f"Technical setups before RS/SCTR/exchange: **{res['technical']}**. RS rejected **{res['rejected_rs']}**; SCTR rejected **{res['rejected_scores']}**; exchange rejected/unknown **{res['exchange_rejected']}**.")
        st.markdown('**First Pullback 20W MA**: completed WEEKLY candles only; breakout over a previous N-week high, at least several weekly candles of advance, min impulse, no interim pullback to the 20-week MA tolerance zone, a rising MA, and the first near/touch/bounce. WATCH is not a trigger; FIRST TOUCH is a support-test candidate; BOUNCE requires a weekly close above the touch-week high. Entry/stop are reference levels, not filled orders.\n\n**VCP** = a 2-stage contraction proxy: final N-bar range smaller than preceding N-bar range, intrabar true range contracting, optional volume dry-up. Pivot is the high of the FINAL tight range, not the absolute high of the whole base. VCP breakout requires its own smaller confirmation percentage; stop uses a buffer under final contraction low. **Darvas** remains a separate rule family.\n\n**Box range** = (upper − lower) / lower across preceding N bars (wick high/low by default). **Breakout** = completed candle close at least X% above resistance; its candle is excluded from the box. **Close strength** = (close − low) / (high − low) on breakout candle. **Volume** = change vs immediately prior bar. **Initial stop** = box bottom + 33% × box height (long); **risk** uses entry beyond breakout close. **RS 3M** = return of (stock close / benchmark close) ratio over 13 weekly or 63 daily bars. **RS rank** = percentile within downloaded universe (not proprietary SCTR).')
        st.caption('Prior pivot shown in yellow is an earlier *confirmed swing-high reference*, not the box ceiling; it can already have been breached. Highest close resistance is an experimental early-warning alternative, NOT a classic Darvas breakout. Weekly scans omit an incomplete current week. Historical 412% return reported in the video is NOT reproduced by this app; this is a current screener, not a point-in-time survivorship-free portfolio backtest. Free public sources can be delayed, incomplete, adjusted or rate-limited. No market-cap filter is applied.')
else:
    st.info('Choose a quick preset, provide an SCTR universe or custom tickers, then click **RUN SCREENER**. No synthetic results are shown.')

st.markdown('''<div style="border-top:1px solid #273b4b;margin-top:18px;padding-top:12px;color:#8398ad;font-size:12px">DARVAS RS • Technical research dashboard • Not investment advice • Does not place orders • SCTR requires imported StockCharts snapshot</div>''',unsafe_allow_html=True)
