import pandas as pd, numpy as np, re, json, warnings
warnings.filterwarnings('ignore')
pd.set_option('display.width',200)
R={}  # results for report
def tstat(x):
    x=pd.Series(x).dropna(); n=len(x)
    if n<3: return (np.nan,np.nan,n)
    return (x.mean(), x.mean()/(x.std(ddof=1)/np.sqrt(n)), n)
def fm(df,group,col,by='wk'):
    """Fama-MacBeth: average col per (group, week) first, then t over weeks."""
    g=df.groupby([group,by])[col].mean().reset_index()
    return g.groupby(group)[col].agg(mean='mean',t=lambda s: s.mean()/(s.std(ddof=1)/np.sqrt(len(s))) if len(s)>2 else np.nan,weeks='count')

# ---------- prices ----------
yf=pd.read_csv('yf_prices.csv'); db=pd.read_csv('ohlc.csv')[['ticker','date','close']]
db['ticker']=db.ticker.astype(str); yf['ticker']=yf.ticker.astype(str)
yf_t=set(yf.ticker)
px=pd.concat([yf, db[~db.ticker.isin(yf_t)]]).drop_duplicates(['ticker','date']).sort_values(['ticker','date'])
px['date']=pd.to_datetime(px.date)
series={t:g.set_index('date').close for t,g in px.groupby('ticker')}
bench={'TW':series['^TWII'],'US':series['^GSPC']}
def is_tw(t): return bool(re.fullmatch(r'\d{4,6}[A-Z]?',str(t)))

def fwd(s,dates,h):
    """forward h-trading-day return from first close strictly after each date."""
    idx=s.index; pos=idx.searchsorted(dates,side='right')  # first close after date
    out=np.full(len(dates),np.nan); ok=(pos+h<len(idx))
    v=s.values; p=pos[ok]; out[ok]=v[p+h]/v[p]-1
    return out, np.where(pos<len(idx),idx[np.minimum(pos,len(idx)-1)],pd.NaT)
def back(s,dates,h):
    idx=s.index; pos=idx.searchsorted(dates,side='right'); out=np.full(len(dates),np.nan)
    ok=(pos-h>=0)&(pos<len(idx)); p=pos[ok]; v=s.values; out[ok]=v[p]/v[p-h]-1; return out
def range_pos(s,dates,h=60):
    """where the entry close sits inside the trailing h-day high/low range (0=low,1=high)."""
    idx=s.index; pos=idx.searchsorted(dates,side='right'); out=np.full(len(dates),np.nan)
    v=s.values
    for k,p in enumerate(pos):
        if p<h or p>=len(idx): continue
        w=v[p-h:p+1]; lo,hi=w.min(),w.max(); out[k]=(v[p]-lo)/(hi-lo) if hi>lo else 0.5
    return out
def fwd_extreme(s,dates,h=60):
    """max drawup / max drawdown over next h days from entry."""
    idx=s.index; pos=idx.searchsorted(dates,side='right'); up=np.full(len(dates),np.nan); dn=up.copy(); v=s.values
    for k,p in enumerate(pos):
        if p+h>=len(idx): continue
        w=v[p:p+h+1]; up[k]=w.max()/v[p]-1; dn[k]=w.min()/v[p]-1
    return up,dn

# ---------- mentions ----------
m=pd.read_csv('insights.csv'); m['ticker']=m.ticker.astype(str)
m['t']=pd.to_datetime(m.launch_time,utc=True,format='ISO8601').dt.tz_convert('Asia/Taipei')
m['date']=m.t.dt.tz_localize(None).dt.normalize()
m['mkt']=np.where(m.ticker.map(is_tw),'TW',np.where(m.market=='US','US','OTHER'))
m=m[m.mkt.isin(['TW','US'])].copy()
m['stance']=m.label.map({'STRONG_BULLISH':'bull','BULLISH':'bull','NEUTRAL':'neutral','BEARISH':'bear','STRONG_BEARISH':'bear'})
m['wk']=m.date.dt.to_period('W-SUN').dt.start_time
m['has_px']=m.ticker.isin(series.keys())
R['coverage']={'insights_TW_US':len(m),'with_price':int(m.has_px.sum()),'tickers_with_price':int(m[m.has_px].ticker.nunique())}
for h in (5,20,60):
    m[f'r{h}']=np.nan; m[f'x{h}']=np.nan
m['b20']=np.nan; m['b60']=np.nan; m['rp60']=np.nan; m['up60']=np.nan; m['dn60']=np.nan
for t,g in m[m.has_px].groupby('ticker'):
    s=series[t]; b=bench[g.mkt.iloc[0]]; d=g.date.values
    for h in (5,20,60):
        r,_=fwd(s,d,h); rb,_=fwd(b,d,h); m.loc[g.index,f'r{h}']=r; m.loc[g.index,f'x{h}']=r-rb
    m.loc[g.index,'b20']=back(s,d,20); m.loc[g.index,'b60']=back(s,d,60); m.loc[g.index,'rp60']=range_pos(s,d,60)
    up,dn=fwd_extreme(s,d,60); m.loc[g.index,'up60']=up; m.loc[g.index,'dn60']=dn
mp=m[m.r20.notna()].copy()
print('mentions with r20:',len(mp),'r60:',m.r60.notna().sum(), 'period',mp.date.min().date(),mp.date.max().date())

# ---------- descriptive ----------
R['label_mix']=m.label.value_counts().to_dict()
R['stance_by_market']=m.groupby('mkt').stance.value_counts(normalize=True).unstack().round(3).to_dict()
R['horizon_by_stance']=m.groupby('stance').horizon.value_counts(normalize=True).unstack().round(3).to_dict()
sc=pd.to_numeric(m.score,errors='coerce'); R['score_dist']=sc.round(1).value_counts().sort_index().to_dict()
R['score_by_label']=m.assign(s=sc).groupby('label').s.describe()[['count','mean','50%','max']].round(3).to_dict()
print('\n== stance × market'); print(pd.DataFrame(R['stance_by_market']))
print('\n== score by label'); print(pd.DataFrame(R['score_by_label']))

# ---------- T1 stance → forward excess ----------
print('\n== T1 stance → forward return (raw / excess vs index), pooled; t = pooled t; FM t = Fama-MacBeth by week')
rows=[]
for mk in ('TW','US','ALL'):
    d=mp if mk=='ALL' else mp[mp.mkt==mk]
    for st in ('bull','neutral','bear'):
        g=d[d.stance==st]
        for h in (5,20,60):
            mu,t,n=tstat(g[f'x{h}']); mr,_,_=tstat(g[f'r{h}'])
            hit=(g[f'r{h}']>0).mean(); xhit=(g[f'x{h}']>0).mean()
            rows.append(dict(mkt=mk,stance=st,h=h,n=n,raw=mr*100,hit=hit*100,excess=mu*100,xhit=xhit*100,t=t))
T1=pd.DataFrame(rows); print(T1.round(2).to_string())
R['T1']=T1.round(3).to_dict('records')
f=fm(mp[mp.stance.isin(['bull','bear'])],'stance','x20'); print('\nFM by week, x20:'); print(f.round(4)); R['T1_fm']=f.round(4).to_dict()
# bull hit rate vs index-up base rate
R['beta_check']={}
for mk in ('TW','US'):
    g=mp[(mp.mkt==mk)&(mp.stance=='bull')]
    b=bench[mk]; rb,_=fwd(b,g.date.values,20)
    R['beta_check'][mk]={'bull_hit_r20':round((g.r20>0).mean()*100,1),'index_up_r20':round((rb>0).mean()*100,1),'bull_hit_excess':round((g.x20>0).mean()*100,1),'n':len(g)}
print('\nbeta check',R['beta_check'])

# ---------- T2 score strength ----------
print('\n== T2 score / strength (bull only) → excess r20, r60')
mp['s']=pd.to_numeric(mp.score,errors='coerce')
mp['sbin']=pd.cut(mp.s,[0,0.55,0.65,0.75,0.85,1.01],labels=['≤.55','.56-.65','.66-.75','.76-.85','>.85'])
T2=mp[mp.stance=='bull'].groupby('sbin',observed=True).agg(n=('x20','size'),x20=('x20','mean'),x60=('x60','mean'),hit20=('x20',lambda s:(s>0).mean()))
T2b=mp[mp.stance=='bull'].groupby('label').agg(n=('x20','size'),x20=('x20','mean'),x60=('x60','mean'),hit20=('x20',lambda s:(s>0).mean()))
print((T2*[1,100,100,100]).round(2)); print((T2b*[1,100,100,100]).round(2))
R['T2']=(T2*[1,100,100,100]).round(2).reset_index().astype({'sbin':str}).to_dict('records'); R['T2_label']=(T2b*[1,100,100,100]).round(2).reset_index().to_dict('records')

# ---------- T3 horizon ----------
print('\n== T3 horizon × stance → excess r20 / r60 (hit% = excess>0 for bull, <0 for bear)')
rows=[]
for st in ('bull','bear'):
    for hz in ('短期','中期','長期'):
        g=mp[(mp.stance==st)&(mp.horizon==hz)]; sg=1 if st=='bull' else -1
        rows.append(dict(stance=st,horizon=hz,n=len(g),x20=g.x20.mean()*100,hit20=((sg*g.x20)>0).mean()*100,n60=g.x60.notna().sum(),x60=g.x60.mean()*100,hit60=((sg*g.x60.dropna())>0).mean()*100,t20=tstat(g.x20)[1],t60=tstat(g.x60)[1]))
T3=pd.DataFrame(rows); print(T3.round(2).to_string()); R['T3']=T3.round(2).to_dict('records')

# ---------- T4 reason categories ----------
print('\n== T4 reason category (bull mentions) → excess r20/r60; category present in reasons[]')
cats=['FUNDAMENTAL','DEMAND','TECHNICAL','MOAT','OPERATIONAL','MACRO','VALUATION','SUPPLY','PRICE_ACTION']
rows=[]
bull=mp[mp.stance=='bull']
for c in cats:
    has=bull.categories.fillna('').str.upper().str.contains(c)
    g=bull[has]; o=bull[~has]
    rows.append(dict(cat=c,n=len(g),share=len(g)/len(bull)*100,x20=g.x20.mean()*100,x20_other=o.x20.mean()*100,x60=g.x60.mean()*100,x60_other=o.x60.mean()*100,t20=tstat(g.x20)[1],t60=tstat(g.x60)[1],hit60=(g.x60.dropna()>0).mean()*100))
T4=pd.DataFrame(rows); print(T4.round(2).to_string()); R['T4']=T4.round(2).to_dict('records')
cyc=['MACRO','DEMAND','SUPPLY','VALUATION','TECHNICAL','PRICE_ACTION']; strc=['MOAT','OPERATIONAL']
u=bull.categories.fillna('').str.upper()
bull=bull.assign(cyc=u.apply(lambda s: any(c in s for c in cyc)),strc=u.apply(lambda s: any(c in s for c in strc)))
bull['bucket']=np.select([bull.cyc&~bull.strc,bull.strc&~bull.cyc,bull.cyc&bull.strc],['cyclical_only','structural_only','both'],'neither')
T4b=bull.groupby('bucket').agg(n=('x20','size'),x20=('x20','mean'),x60=('x60','mean'),hit60=('x60',lambda s:(s.dropna()>0).mean()),t60=('x60',lambda s:tstat(s)[1]))
print((T4b*[1,100,100,100,1]).round(2)); R['T4_bucket']=(T4b*[1,100,100,100,1]).round(2).reset_index().to_dict('records')
# thesis keyword: 缺貨/漲價 (short supply) vs 轉型/結構 
kw={'缺貨/漲價':r'缺貨|漲價|供不應求|急單','結構/轉型':r'結構|轉型|長期|典範|世代','法說/財報':r'法說|財報|EPS|營收','題材/概念':r'題材|概念股|族群'}
rows=[]
for k,p in kw.items():
    g=bull[bull.thesis.fillna('').str.contains(p)]
    rows.append(dict(kw=k,n=len(g),x20=g.x20.mean()*100,x60=g.x60.mean()*100,hit60=(g.x60.dropna()>0).mean()*100,t60=tstat(g.x60)[1]))
T4c=pd.DataFrame(rows); print(T4c.round(2).to_string()); R['T4_kw']=T4c.round(2).to_dict('records')

# ---------- weekly panel ----------
wk=m.groupby(['ticker','wk']).agg(n=('episode_id','size'),shows=('podcaster','nunique'),bull=('stance',lambda s:(s=='bull').sum()),bear=('stance',lambda s:(s=='bear').sum()),mkt=('mkt','first')).reset_index()
# full calendar per ticker between first and last mention week (zeros where absent)
full=[]
for t,g in wk.groupby('ticker'):
    if t not in series: continue
    idx=pd.date_range(g.wk.min(),g.wk.max(),freq='7D')
    gg=g.set_index('wk').reindex(idx).fillna({'n':0,'shows':0,'bull':0,'bear':0}); gg['ticker']=t; gg['mkt']=g.mkt.iloc[0]
    gg.index.name='wk'; full.append(gg.reset_index())
W=pd.concat(full).sort_values(["ticker","wk"]).reset_index(drop=True)
W['trail8']=W.groupby('ticker').n.transform(lambda s:s.shift(1).rolling(8,min_periods=4).mean())
W['trail8sd']=W.groupby('ticker').n.transform(lambda s:s.shift(1).rolling(8,min_periods=4).std())
W['z']=(W.n-W.trail8)/(W.trail8sd.replace(0,np.nan))
W['n4']=W.groupby('ticker').n.transform(lambda s:s.rolling(4,min_periods=1).sum())
W['prev4']=W.groupby('ticker').n4.transform(lambda s:s.shift(4))
W['cum52']=W.groupby('ticker').n.transform(lambda s:s.shift(1).rolling(52,min_periods=1).sum())
# price features from week end (sunday) -> entry next trading close
W['wend']=W.wk+pd.Timedelta(days=6)
for c in ('f20','f60','xf20','xf60','b20','b60','rp60','up60','dn60','f120','xf120'): W[c]=np.nan
for t,g in W.groupby('ticker'):
    s=series[t]; b=bench[g.mkt.iloc[0]]; d=g.wend.values
    for h,(fc,xc) in {20:('f20','xf20'),60:('f60','xf60'),120:('f120','xf120')}.items():
        r,_=fwd(s,d,h); rb,_=fwd(b,d,h); W.loc[g.index,fc]=r; W.loc[g.index,xc]=r-rb
    W.loc[g.index,'b20']=back(s,d,20); W.loc[g.index,'b60']=back(s,d,60); W.loc[g.index,'rp60']=range_pos(s,d,60)
    up,dn=fwd_extreme(s,d,60); W.loc[g.index,'up60']=up; W.loc[g.index,'dn60']=dn
Wp=W[W.f20.notna()].copy()
Wp['era']=np.where(Wp.wk<'2025-08-01','2020-25 (股癌等, 124檔)','2025-08+ (全部節目, 全市場)')
print('\nweekly panel rows',len(Wp),'tickers',Wp.ticker.nunique())

# ---------- T5 mention intensity ----------
print('\n== T5 mention intensity: z-score of weekly mentions vs trailing 8w → forward excess')
Wz=Wp[Wp.z.notna()&(Wp.n>0)].copy()
Wz['zbin']=pd.cut(Wz.z,[-np.inf,-0.5,0.5,1.5,2.5,np.inf],labels=['<-0.5','-0.5~0.5','0.5~1.5','1.5~2.5','>2.5'])
def panel_tab(d,key):
    g=d.groupby(key,observed=True).agg(n=('xf20','size'),xf20=('xf20','mean'),xf60=('xf60','mean'),hit60=('xf60',lambda s:(s.dropna()>0).mean()),t20=('xf20',lambda s:tstat(s)[1]),t60=('xf60',lambda s:tstat(s)[1]),b20=('b20','mean'),rp60=('rp60','mean'))
    return (g*[1,100,100,100,1,1,100,1]).round(2)
for era,d in Wz.groupby('era'):
    print('--',era); print(panel_tab(d,'zbin'))
    R.setdefault('T5',{})[era]=panel_tab(d,'zbin').reset_index().astype({'zbin':str}).to_dict('records')
# spike: n >= max(3, 2*trail8) 
Wp['spike']=(Wp.n>=3)&(Wp.n>=2*Wp.trail8.fillna(0))&(Wp.trail8.notna())
print('\n== T5b spike (n>=3 & >=2× trailing 8w avg) vs non-spike weeks with mentions')
Wm=Wp[Wp.n>0]
for era,d in Wm.groupby('era'):
    print('--',era); print(panel_tab(d,'spike')); R.setdefault('T5b',{})[era]=panel_tab(d,'spike').reset_index().astype({'spike':str}).to_dict('records')

# ---------- T6 turning point test ----------
print('\n== T6 turning point: spike weeks — where is price in trailing 60d range, and what happens next, split by prior 20d momentum')
Ws=Wm[Wm.rp60.notna()].copy()
Ws['pos']=pd.cut(Ws.rp60,[-0.01,0.1,0.9,1.01],labels=['near 60d low','middle','near 60d high'])
Ws['mom']=np.where(Ws.b20>0.10,'up>10%',np.where(Ws.b20<-0.10,'down>10%','flat'))
for era,d in Ws.groupby('era'):
    print('--',era)
    print('range position share: spike vs non-spike'); print(pd.crosstab(d.spike,d.pos,normalize='index').round(3))
    tab=d.groupby(['spike','mom']).agg(n=('xf20','size'),xf20=('xf20','mean'),xf60=('xf60','mean'),t20=('xf20',lambda s:tstat(s)[1]),t60=('xf60',lambda s:tstat(s)[1]),up60=('up60','mean'),dn60=('dn60','mean'))
    tab=(tab*[1,100,100,1,1,100,100]).round(2); print(tab)
    R.setdefault('T6',{})[era]={'pos':pd.crosstab(d.spike,d.pos,normalize='index').round(3).reset_index().astype({'spike':str}).to_dict('records'),'mom':tab.reset_index().astype({'spike':str}).to_dict('records')}
    # amplitude: |f60| for spike vs not (turning point ⇒ bigger move either way?)
    a=d.groupby('spike').apply(lambda g: pd.Series({'abs_xf60':g.xf60.abs().mean()*100,'swing60':(g.up60-g.dn60).mean()*100,'n':len(g)})).round(2); print(a)
    R['T6'][era]['amp']=a.reset_index().astype({'spike':str}).to_dict('records')

# ---------- T7 attention decay ----------
print('\n== T7 attention decay: n4 (last 4 wks) fell ≥50% from prev4 which was ≥6 → forward excess vs. other weeks')
Wp['decay']=(Wp.prev4>=6)&(Wp.n4<=0.5*Wp.prev4)
Wp['rising']=(Wp.prev4>=2)&(Wp.n4>=2*Wp.prev4)&(Wp.n4>=6)
Wp['state']=np.select([Wp.decay,Wp.rising],['decay','rising'],'other')
for era,d in Wp.groupby('era'):
    print('--',era); print(panel_tab(d,'state')); R.setdefault('T7',{})[era]=panel_tab(d,'state').reset_index().to_dict('records')
f=fm(Wp,'state','xf20'); print('FM by week xf20:'); print(f.round(4)); R['T7_fm']=f.round(4).reset_index().to_dict('records')

# ---------- T8 breadth ----------
print('\n== T8 breadth: distinct shows bullish in the week (2025-08+ only, when all shows exist)')
d=Wm[Wm.era.str.startswith('2025')].copy()
d['bshows']=pd.cut(d.bull,[-1,0,1,2,3,99],labels=['0','1','2','3','4+'])
print(panel_tab(d,'bshows')); R['T8']=panel_tab(d,'bshows').reset_index().astype({'bshows':str}).to_dict('records')
d['bearany']=d.bear>0
print('any bear mention in week:'); print(panel_tab(d,'bearany')); R['T8_bear']=panel_tab(d,'bearany').reset_index().astype({'bearany':str}).to_dict('records')

# ---------- T9 novelty ----------
print('\n== T9 novelty: first mention after ≥12 quiet weeks (cum52 small) vs. heavily-covered')
Wm2=Wm[Wm.era.str.startswith('2025')].copy()
Wm2['prior']=pd.cut(Wm2.cum52,[-1,0,3,10,30,999],labels=['0 (new)','1-3','4-10','11-30','30+'])
print(panel_tab(Wm2,'prior')); R['T9']=panel_tab(Wm2,'prior').reset_index().astype({'prior':str}).to_dict('records')

# ---------- T11 per-show hit rate raw vs excess ----------
print('\n== T11 per-show: bull hit rate raw vs excess (r20), n≥60')
g=mp[mp.stance=='bull'].groupby('podcaster').agg(n=('r20','size'),raw_hit=('r20',lambda s:(s>0).mean()*100),x_hit=('x20',lambda s:(s>0).mean()*100),x20=('x20',lambda s:s.mean()*100),x60=('x60',lambda s:s.mean()*100))
g=g[g.n>=60].sort_values('x20',ascending=False).round(1); print(g); R['T11']=g.reset_index().to_dict('records')

# ---------- T10 case studies ----------
cs={}
for t in ('2330','NVDA','TSLA','2454','3037','2408'):
    if t not in series: continue
    s=series[t]; ms=m[m.ticker==t].groupby(m.date.dt.to_period('M')).size()
    mon=s.resample('ME').last(); mon.index=mon.index.to_period('M')
    df=pd.DataFrame({'close':mon,'mentions':ms}).fillna({'mentions':0}); df=df[df.index>='2020-01']
    cs[t]=[{'m':str(k),'close':round(float(v.close),2) if pd.notna(v.close) else None,'n':int(v.mentions)} for k,v in df.iterrows()]
    # correlation of mention z (monthly) with next-3-month return
    df['f3']=df.close.shift(-3)/df.close-1; df['b3']=df.close/df.close.shift(3)-1
    df['mz']=(df.mentions-df.mentions.rolling(6).mean())/df.mentions.rolling(6).std()
    print(t,'corr(mz, fwd3m)=%.2f corr(mz, back3m)=%.2f n=%d'%(df.mz.corr(df.f3),df.mz.corr(df.b3),df.mz.notna().sum()))
R['cases']=cs
json.dump(R,open('results.json','w'),ensure_ascii=False,default=lambda o: None if pd.isna(o) else o)
mp.to_pickle('mp.pkl'); Wp.to_pickle('Wp.pkl')
