# DARVAS RS — v5 · Weekly First Pullback to 20 MA

Actualizare pentru proiectul Streamlit existent `OanaSonic/darvas-rs-screener`. Nu crea un repository nou.

## Nou: prima revenire la 20-week MA după breakout (exemplu: MA)

În `Strategy / setup to scan` (când `Timeframe = Weekly`) alegi:

- `Darvas + VCP` — modurile anterioare, pe Weekly sau Daily;
- `First Pullback to 20W MA` — **exclusiv pe Weekly**;
- `All (Darvas/VCP + First Pullback)` — rezultatele ambelor familii de strategii, inclusiv două rânduri pentru același simbol dacă apar ambele tipuri de setup.

Detectorul First Pullback are următoarele condiții mecanice, configurabile din interfață:

1. Prețul **închide deasupra maximului celor N săptămâni precedente** (8 implicit), cu clearance minim 0,5%, iar baza anterioară nu este excesiv de largă (implicit maxim 35%). Acesta e un proxy algoritmic pentru breakout, nu copiere exactă a unui breakout desenat discreționar.
2. Urmează cel puțin **3 săptămâni complete de avans înaintea pullback-ului**, în intervalul de cel mult 16 săptămâni de la breakout. Impulsul trebuie să atingă cel puțin +8% față de close-ul breakout-ului.
3. În săptămânile dintre breakout și retest, **minimele nu au atins încă banda de toleranță** a mediei de 20 de săptămâni: săptămâna detectată este prima apropiere relevantă de medie.
4. Media **20W EMA** (implicit) sau **20W SMA** este în creștere față de acum 3 săptămâni.
5. Categoriile sunt:
   - `PULLBACK WATCH`: ultimul Low săptămânal este la 2–5% peste medie, neatinse încă. **Nu reprezintă un trigger de intrare**, Entry/Stop/Risk rămân N/A.
   - `FIRST MA TOUCH`: Low se află la maximum +2% deasupra / −2,5% sub medie, iar închiderea rămâne aproape deasupra acesteia. Entry **prospectiv** = maximul săptămânii de retest + buffer de 0,1%; stop orientativ sub minimul săptămânii −0,5%.
   - `BOUNCE CONFIRMED`: una dintre următoarele 1–2 săptămâni **închide peste maximul săptămânii primului touch** și peste MA 20W, fără să o străpungă masiv. Entry/Stop reprezintă nivelurile trigger-ului și invalidării, **nu ordine executate**.
6. Filtrele SCTR (import/paste din StockCharts), RS vs SPY/SPX și RSI ranking (rank din RS, nu RSI indicator) sunt păstrate; datele Yahoo publice pot fi întârziate. `Breakout freshness: last N bars` funcționează și pentru vechimea semnalelor de pullback.

**Grafic la hover** pentru pullback: lumânări săptămânale, EMA/SMA 20W, nivelul breakout-ului anterior, data breakout-ului, marcajul pentru primul retest/atingere și pentru bounce, volum și RS vs benchmark. Pentru Darvas/VCP rămân box-urile anterioare. Dacă un ticker are 2 strategii, hover afișează **graficul rândului corespunzător**, nu primul rând cu acel ticker.

## Alte modificări păstrate din v4

- **Fără Market Cap** și fără interogări Yahoo pentru capitalizare; lipsa metadatelor cap nu elimină tickere. SCTR nu este o garanție că un simbol e large cap.
- **Fără Barchart, Quality și Growth** din tabel, interfață și CSV.
- `BREAKOUT`, `PRE-BREAKOUT`, `IN BOX` și `VCP / tight base` pe Weekly/Daily.
- În tabel: signal age, last close, extension from entry, SCTR și relative strength; hover pe ticker pentru grafic, click pentru fixare.
- VCP folosește numai ultima contracție drept box de intrare, diferită de box-ul clasic Darvas.

## Instalare în repository-ul existent

1. Dezarhivează ZIP-ul și încarcă fișierele din rădăcina arhivei la `github.com/OanaSonic/darvas-rs-screener` → **Add file → Upload files**.
2. Înlocuiește `app.py`, `screener_core.py`, `hover_chart.py`, `sctr_paste.py`, `README.md`, `requirements.txt`. **Adaugă obligatoriu noul `pullback_core.py`** la același nivel cu `app.py`. Fișierele `tests/` sunt opționale pentru deploy. Poți păstra `.streamlit/config.toml` existent.
3. Apasă **Commit changes**. Streamlit Cloud ar trebui să redeployeze automat; dacă nu, `Manage app → Reboot app`.
4. Alege `Weekly`, `First Pullback to 20W MA` și `Imported SCTR list` cu textul lipit din StockCharts. Lasă `RS` activ. Folosește `Max tickers` corespunzător listei importate.

### Limitări

Nu este o certificare Minervini/VCP și nu face backtest al tranzacțiilor: prețul de intrare teoretic nu presupune că ordinul a fost executat. Datele istorice sunt ajustate și posibil întârziate; săptămâna în curs este omisă când `Completed candles only` e activ. Scannerul poate să rateze consolidări desenate manual sau să semnaleze configurări mecanic valide dar slabe fundamental. Urmărește graficul și riscul înainte de orice tranzacție.

Testare locală: `pip install -r requirements.txt`, apoi `streamlit run app.py`; teste `python -m pytest -q` (pytest e opțional).
