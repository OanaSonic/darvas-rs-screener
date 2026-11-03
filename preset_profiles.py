"""User-facing, transparent technical screening starting configurations.

The presets express research preferences, not backtested trading performance.
Saved personal profiles hold the same validated, JSON-serializable filters.
"""
from __future__ import annotations
from copy import deepcopy
import json
import re
import math

PROFILE_FORMAT_VERSION = 1

DEFAULT_FILTERS = {
    # Quick filters
    'timeframe': 'Weekly', 'benchmark': 'SPY', 'lookback': 3,
    'sctr_min': 70, 'rs_mode': '3M outperform', 'sctr_on': False,
    # Universe, family, signal
    'direction':'Long', 'mode_label':'Breakout only', 'family_choice':'Darvas Box only',
    'exchange_filter':[],
    # Darvas
    'min_bars':6, 'max_bars':16, 'max_box':20.0, 'stop_pos':33,
    'max_risk':16.0, 'breakout_min':1.0, 'breakout_max':10.0,
    'close_strength':75, 'min_volume':1.0, 'entry_buffer':0.01,
    'ema_on':True, 'macd_on':True, 'touches':1, 'touch_tol':2.5,
    'near_distance':5.0, 'max_inside_distance':20.0,
    'resistance_basis':'Highest wick (range box)',
    'confirmed_pivot':False, 'completed_only':True,
    # VCP
    'vcp_tight':12.0, 'vcp_range':0.80, 'vcp_atr':0.95, 'vcp_clear':0.15,
    'vcp_dry':True, 'vcp_vol':0.90, 'vcp_stop':0.30,
    # First pullback, weekly
    'pb_ma':'EMA', 'pb_stage':'All', 'pb_upweeks':3, 'pb_maxweeks':16,
    'pb_advance':8.0, 'pb_touch':2.0, 'pb_watch':5.0,
    'pb_undercut':2.5, 'pb_breakperiod':8, 'pb_breakclear':0.5,
    'pb_stop':0.5, 'pb_risk':16.0,
    # Extra RS
    'rs_min':0.0, 'rs_pctl':0,
}

RECOMMENDED_PRESETS = {
    'Darvas Breakout': {
        'strategy': 'Darvas + VCP',
        'description': 'Weekly · box ≥6 lumânări · breakout ≥1% și ≤10% · close strength ≥75% · EMA20 + MACD · SCTR ≥70 · RS 3M pozitiv.',
        'overrides': {
            'timeframe':'Weekly', 'lookback':2, 'mode_label':'Breakout only',
            'family_choice':'Darvas Box only', 'min_bars':6, 'max_bars':16,
            'max_box':20.0, 'breakout_min':1.0, 'breakout_max':10.0,
            'close_strength':75, 'min_volume':1.0,
            'ema_on':True, 'macd_on':True,
        },
    },
    'VCP Pre-Breakout': {
        'strategy': 'Darvas + VCP',
        'description': 'Weekly · ultima contracție ≤12% · range ratio ≤0,80 · volum în scădere · pivot apropiat · SCTR ≥70 · RS 3M pozitiv.',
        'overrides': {
            'timeframe':'Weekly', 'lookback':3, 'mode_label':'Pre-Breakout only',
            'family_choice':'Tight Base / VCP only', 'min_bars':4, 'max_bars':16,
            'close_strength':60, 'min_volume':0.0, 'ema_on':True, 'macd_on':False,
            'vcp_tight':12.0, 'vcp_range':0.8, 'vcp_atr':0.95,
            'vcp_dry':True, 'vcp_vol':0.9, 'near_distance':5.0,
        },
    },
    'First Pullback EMA 20W': {
        'strategy': 'First Pullback to 20W MA',
        'description': 'Doar Weekly · breakout anterior (8W) · ≥3 săptămâni de trend · impuls ≥8% · prima apropiere/atingere EMA20W · SCTR ≥70.',
        'overrides': {
            'timeframe':'Weekly','lookback':3,
            'mode_label':'Both (Breakout + Pre-Breakout)',
            'family_choice':'Both (Darvas + Tight VCP)',
            'pb_ma':'EMA', 'pb_stage':'All', 'pb_upweeks':3,
            'pb_maxweeks':16,'pb_advance':8.0,'pb_touch':2.0,
            'pb_watch':5.0,'pb_undercut':2.5,
            'pb_breakperiod':8,'pb_breakclear':0.5,
            'pb_stop':0.5,'pb_risk':16.0,
        },
    },
}


def recommended_profile(name: str, imported_sctr: bool = False) -> dict:
    if name not in RECOMMENDED_PRESETS:
        raise ValueError('Preset necunoscut')
    config = deepcopy(DEFAULT_FILTERS)
    config.update(deepcopy(RECOMMENDED_PRESETS[name]['overrides']))
    config['sctr_on'] = bool(imported_sctr)
    return config


def validate_profile(base_name: str, profile: dict) -> dict:
    """Safely accept saved profile values without arbitrary keys/types."""
    if base_name not in RECOMMENDED_PRESETS or not isinstance(profile,dict):
        raise ValueError('Profil necunoscut sau invalid')
    known = recommended_profile(base_name)
    if set(profile)-set(known):
        raise ValueError('Profilul conține filtre necunoscute')
    out=deepcopy(known)
    for k, value in profile.items():
        prior=known[k]
        if isinstance(prior,bool):
            if type(value) is not bool:raise ValueError(f'{k}: trebuie boolean')
        elif isinstance(prior,int):
            if type(value) is not int:raise ValueError(f'{k}: trebuie întreg')
        elif isinstance(prior,float):
            if type(value) not in (int,float):raise ValueError(f'{k}: trebuie număr')
            value=float(value)
        elif isinstance(prior,str):
            if type(value) is not str or len(value)>100:raise ValueError(f'{k}: text invalid')
        elif isinstance(prior,list):
            if type(value) is not list or any(type(v) is not str for v in value):
                raise ValueError(f'{k}: selecție invalidă')
        out[k]=value
    select_options = {
        'timeframe': {'Daily','Weekly'},
        'benchmark': {'SPY','SPX (^GSPC)'},
        'lookback': {1,2,3,5,10,20},
        'rs_mode': {'3M outperform','Off','52w RS high','3M outperform + 52w high'},
        'direction': {'Long','Short'},
        'mode_label': {'Both (Breakout + Pre-Breakout)','Breakout only','Pre-Breakout only','All incl. Inside Box'},
        'family_choice': {'Darvas Box only','Tight Base / VCP only','Both (Darvas + Tight VCP)'},
        'resistance_basis': {'Highest wick (range box)','Highest close (early-warning, non-classic)'},
        'pb_ma': {'EMA','SMA'},
        'pb_stage': {'All','Watch','First touch','Bounce'},
    }
    for field, options in select_options.items():
        if out[field] not in options:
            raise ValueError(f'{field}: alegere neacceptată')
    if out['direction']=='Short' and base_name!='Darvas Breakout':
        raise ValueError('Short este disponibil doar pentru Darvas Breakout')
    if any(e not in {'NASDAQ','NYSE','AMEX','NYSE Arca'} for e in out['exchange_filter']):
        raise ValueError('Filtru bursă necunoscut')
    ranges={
        'sctr_min':(0,100), 'min_bars':(3,52), 'max_bars':(3,80),
        'max_box':(1,100),'stop_pos':(0,100),'max_risk':(1,100),
        'breakout_min':(0,40),'breakout_max':(.5,1000),
        'close_strength':(0,100),'min_volume':(-100,1000),
        'entry_buffer':(0,10),'touches':(1,8),'touch_tol':(.1,10),
        'near_distance':(.1,30),'max_inside_distance':(5,100),
        'vcp_tight':(1,40),'vcp_range':(.1,1), 'vcp_atr':(.1,1.5),
        'vcp_clear':(0,10),'vcp_vol':(.1,2),'vcp_stop':(0,5),
        'pb_upweeks':(2,10),'pb_maxweeks':(4,36),'pb_advance':(2,100),
        'pb_touch':(0,10),'pb_watch':(2,20),'pb_undercut':(0,12),
        'pb_breakperiod':(4,20),'pb_breakclear':(0,10),
        'pb_stop':(0,10),'pb_risk':(1,40),
        'rs_min':(-100,1000),'rs_pctl':(0,100),
    }
    for field,(low,high) in ranges.items():
        if not math.isfinite(out[field]) or not low<=out[field]<=high:
            raise ValueError(f'{field}: în afara intervalului permis')
    if base_name=='First Pullback EMA 20W' and out['timeframe'] != 'Weekly':
        raise ValueError('First Pullback funcționează doar pe Weekly')
    if out['min_bars']>out['max_bars'] or out['breakout_min']>out['breakout_max']:
        raise ValueError('Limite necompatibile')
    if out['pb_watch']<out['pb_touch'] or out['pb_maxweeks']<=out['pb_upweeks']:
        raise ValueError('Parametri de pullback necompatibili')
    return out


def export_user_profiles(profiles: dict) -> str:
    content={}
    for name,raw in profiles.items():
        if not re.fullmatch(r'[\w .\-]{1,45}',name,flags=re.UNICODE):continue
        content[name]={'base':raw['base'],'filters':validate_profile(raw['base'],raw['filters'])}
    return json.dumps({'format':'darvas-rs-profiles','version':PROFILE_FORMAT_VERSION,'profiles':content},ensure_ascii=False,indent=2)


def import_user_profiles(content: bytes) -> dict:
    if len(content)>100_000:raise ValueError('Fișierul este prea mare')
    raw=json.loads(content.decode('utf-8-sig'))
    if not isinstance(raw,dict) or raw.get('format')!='darvas-rs-profiles' or raw.get('version')!=PROFILE_FORMAT_VERSION:
        raise ValueError('Format de profil neacceptat')
    rows=raw.get('profiles',{})
    if not isinstance(rows,dict) or len(rows)>30:raise ValueError('Prea multe profiluri')
    result={}
    for name,item in rows.items():
        if not isinstance(name,str) or not re.fullmatch(r'[\w .\-]{1,45}',name,flags=re.UNICODE):
            raise ValueError('Nume profil invalid')
        if not isinstance(item,dict):raise ValueError('Profil invalid')
        base=item.get('base')
        result[name]={'base':base,'filters':validate_profile(base,item.get('filters'))}
    return result

# Streamlit renders each help argument as an info icon next to its filter.
FIELD_HELP = {
 'timeframe':'Weekly = o lumânare pe săptămână; Daily = o lumânare pe zi. First Pullback este numai Weekly.',
 'benchmark':'SPY este ETF-ul care urmărește S&P 500; SPX (^GSPC) este indicele în sine. RS = preț acțiune / benchmark.',
 'lookback':'2 pe Weekly = semnal în ultima sau penultima săptămână închisă. Folosește 1 pentru semnale foarte noi.',
 'sctr_min':'70 = SCTR ≥70 din tabelul StockCharts importat. Acesta este scorul oficial de la momentul copierii.',
 'rs_mode':'3M outperform cere ca raportul acțiune/SPY să fi crescut în aproximativ 13 săptămâni.',
 'sctr_on':'Activ: tickerul trebuie să aibă SCTR importat și să depășească pragul. Inactiv: se pot scana și simboluri fără SCTR.',
 'direction':'Long = breakout ascendent; Short = descendent. Modul VCP și First Pullback sunt Long.',
 'mode_label':'Breakout only = deja a spart rezistența; Pre-Breakout only = încă aproape de pivot.',
 'family_choice':'Darvas = box clasic; VCP = contracția finală, mai mică decât baza precedentă.',
 'exchange_filter':'Gol = nu filtra după bursă; NYSE/NASDAQ restrânge selecția și declanșează verificări suplimentare.',
 'min_bars':'6 pe Weekly = cel puțin 6 săptămâni într-o consolidare. Pentru VCP poți testa 4.',
 'max_bars':'16 pe Weekly = sunt explorate box-uri de cel mult 16 săptămâni.',
 'max_box':'20%: într-un box 100–120 USD, amplitudinea este (120−100)/100 = 20%.',
 'stop_pos':'33% în box 100–120 USD → stop tehnic la 106,60 USD, nu risc de cont 33%.',
 'max_risk':'16% = diferența maximă dintre intrare și stop raportată la prețul de intrare; nu riscul din portofoliu.',
 'breakout_min':'1% = închiderea trebuie să depășească rezistența de 100 USD cu cel puțin 1 USD.',
 'breakout_max':'10% exclude închiderile deja extinse cu peste 10% față de rezistență.',
 'close_strength':'75% = închidere în partea superioară de 25% a lumânării (în raport cu High–Low).',
 'min_volume':'1% = volumul lumânării de semnal e cu ≥1% peste cel anterior; NU este RVOL.',
 'entry_buffer':'0,01% la închidere 100 USD => intrare orientativă 100,01 USD.',
 'ema_on':'Bifat: la Long, închiderea trebuie să fie peste EMA de 20 perioade.',
 'macd_on':'Bifat: linia MACD trebuie să fie peste linia de semnal la Long.',
 'touches':'2 înseamnă că rezistența/suportul trebuie atinse de cel puțin două ori în toleranța permisă.',
 'touch_tol':'2,5% = un High suficient de aproape de rezistență se numără ca atingere.',
 'near_distance':'5%: în pre-breakout, prețul poate fi cu cel mult 5% sub rezistență.',
 'max_inside_distance':'20%: limita pentru a include acțiuni aflate mai jos în interiorul box-ului.',
 'resistance_basis':'Highest wick = maximul High-urilor (Darvas mecanic); Highest close = maximul închiderilor, semnal mai timpuriu.',
 'confirmed_pivot':'Cere trei maxime inferioare după pivot, pentru a confirma o rezistență.',
 'completed_only':'Bifat: ignoră săptămâna în curs; evită semnale care dispar înainte de închidere.',
 'vcp_tight':'12%: intervalul ultimei contracții nu trebuie să depășească 12% din minimul ei.',
 'vcp_range':'0,80: dacă prima parte avea range 15% și ultima 9%, raportul este 0,60 și trece.',
 'vcp_atr':'0,95: True Range mediu din ultima etapă trebuie să fie ≤95% din cel anterior.',
 'vcp_clear':'0,15% = depășire minimă a pivotului local în cazul breakout-ului VCP.',
 'vcp_dry':'Bifat: cere scăderea volumului mediu în ultima parte a consolidării.',
 'vcp_vol':'0,90 înseamnă cel puțin 10% reducere a volumului mediu recent față de perioada precedentă.',
 'vcp_stop':'0,30%: stopul VCP se pune 0,30% sub minimul ultimei contracții.',
 'pb_ma':'EMA = reacționează mai repede la prețurile recente; SMA = media aritmetică pe 20 săptămâni.',
 'pb_stage':'All = WATCH + FIRST TOUCH + BOUNCE. WATCH este doar o situație de urmărit.',
 'pb_upweeks':'3 = după breakout, cel puțin trei săptămâni de avans înainte de primul pullback.',
 'pb_maxweeks':'16 = breakout-ul inițial poate fi la cel mult 16 săptămâni distanță.',
 'pb_advance':'8% = impulsul după breakout trebuie să atingă cel puțin +8%.',
 'pb_touch':'2% = minimul săptămânii poate fi până la 2% deasupra EMA și este considerat în zona atingerii.',
 'pb_watch':'5% = clasifică WATCH când minimul este încă între aproximativ 2% și 5% deasupra EMA.',
 'pb_undercut':'2,5% = minimul poate coborî cel mult 2,5% sub medie, cu condițiile suplimentare din algoritm.',
 'pb_breakperiod':'8 = breakout-ul inițial este peste maximul precedentelor 8 săptămâni.',
 'pb_breakclear':'0,5% = închiderea la breakout-ul inițial depășește rezistența cu cel puțin 0,5%.',
 'pb_stop':'0,5% = stop orientativ sub minimul săptămânii de atingere.',
 'pb_risk':'16% = distanța maximă între intrare și stop la pullback, nu suma riscată din cont.',
 'rs_min':'0% = orice RS 3M pozitiv; 5% = acțiunea depășește benchmark-ul cu cel puțin 5% după calculul raportului.',
 'rs_pctl':'80 = acțiunea se află aproximativ în primele 20% din universul scanat după RS 3M.',
}
