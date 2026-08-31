import os, asyncio, time, json
from datetime import datetime, timezone
import aiohttp, websockets
from dotenv import load_dotenv
load_dotenv()
TG_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN',''); TG_CHAT=os.getenv('TELEGRAM_CHAT_ID','')
NETWORK=os.getenv('NETWORK_ID','robinhood'); SCAN_INTERVAL=int(os.getenv('SCAN_INTERVAL_SECONDS','15'))
MIN_MC=float(os.getenv('MIN_MC','150000')); MAX_MC=float(os.getenv('MAX_MC','1200000')); MIN_LIQ=float(os.getenv('MIN_LIQ','30000'))
MIN_ALERT=int(os.getenv('MIN_ALERT_SCORE','92')); MIN_TRACK=int(os.getenv('MIN_TRACK_SCORE','82')); WALLET=float(os.getenv('WALLET_USD','400')); MAX_POSITION=float(os.getenv('MAX_POSITION_USD','100'))
RPC_WS=os.getenv('RH_RPC_WS',''); GT='https://api.geckoterminal.com/api/v2'; HEADERS={'Accept':'application/json;version=20230203','User-Agent':'RH-Gem-Hunter/1.0'}
seen={}
def num(x,d=0.0):
    try:return float(x) if x not in (None,'') else d
    except:return d
def money(x):
    return f'${x/1_000_000:.2f}M' if x>=1_000_000 else (f'${x/1000:.1f}K' if x>=1000 else f'${x:.0f}')
async def tg(s,text):
    if not TG_TOKEN or not TG_CHAT: print(text); return
    async with s.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',json={'chat_id':TG_CHAT,'text':text,'disable_web_page_preview':True},timeout=15) as r:
        if r.status>=300: print('Telegram error',r.status,await r.text())
async def gt(s,path,params=None):
    async with s.get(GT+path,headers=HEADERS,params=params,timeout=20) as r:
        r.raise_for_status(); return await r.json()
def parse_pool(item):
    a=item.get('attributes',{}) or {}; rel=item.get('relationships',{}) or {}; tx=a.get('transactions',{}) or {}; vol=a.get('volume_usd',{}) or {}; pc=a.get('price_change_percentage',{}) or {}
    def t(w): return tx.get(w,{}) or {}
    base=(((rel.get('base_token') or {}).get('data') or {}).get('id') or ''); token=base.split('_',1)[-1] if '_' in base else base
    age=999999; created=a.get('pool_created_at')
    if created:
        try: age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(created.replace('Z','+00:00'))).total_seconds()/60)
        except: pass
    mc=num(a.get('market_cap_usd')) or num(a.get('fdv_usd'))
    return {'name':a.get('name') or 'UNKNOWN','token':token,'pool':a.get('address') or '','mc':mc,'liq':num(a.get('reserve_in_usd')),'vol5':num(vol.get('m5')),'vol1h':num(vol.get('h1')),'vol24':num(vol.get('h24')),'b5':int(num(t('m5').get('buys'))),'s5':int(num(t('m5').get('sells'))),'b15':int(num(t('m15').get('buys'))),'s15':int(num(t('m15').get('sells'))),'p5':num(pc.get('m5')),'p15':num(pc.get('m15')),'age':age}
def score(c):
    if c['mc']<=0 or c['liq']<MIN_LIQ or c['mc']<75000 or c['mc']>2000000:return 0,['outside universe/thin liquidity']
    s=0; why=[]
    if MIN_MC<=c['mc']<=MAX_MC:s+=20;why.append('MC sweet spot')
    elif 100000<=c['mc']<=1500000:s+=10
    lr=c['liq']/max(c['mc'],1)
    if .08<=lr<=.45:s+=15;why.append('healthy liquidity')
    elif lr>=.05:s+=8
    else:s-=15
    t5=c['b5']+c['s5']; t15=c['b15']+c['s15']
    if t5>=25:s+=12;why.append('strong 5m activity')
    elif t5>=12:s+=7
    br5=c['b5']/max(c['s5'],1)
    if br5>=1.7 and c['b5']>=10:s+=14;why.append('buyers dominate')
    elif br5>=1.3:s+=7
    if t15 and (t5/5)>=(t15/15)*1.5:s+=10;why.append('transactions accelerating')
    if c['vol5']>=12000:s+=10;why.append('5m volume strong')
    elif c['vol5']>=5000:s+=5
    if 1.5<=c['p5']<=15:s+=8;why.append('early momentum')
    elif c['p5']>35:s-=20;why.append('too extended')
    if 3<=c['p15']<=35:s+=5
    elif c['p15']>80:s-=12
    if 3<=c['age']<=240:s+=4
    return max(0,min(100,s)),why
async def discover(s):
    out={}
    for ep in (f'/networks/{NETWORK}/new_pools',f'/networks/{NETWORK}/trending_pools'):
        try:
            for x in (await gt(s,ep,{'page':1})).get('data',[]): out[x.get('id')]=x
        except Exception as e: print('discover error',e)
    return list(out.values())
async def scan(s):
    pools=await discover(s); ranked=[]
    for x in pools:
        c=parse_pool(x); sc,why=score(c)
        if sc>=MIN_TRACK: ranked.append((sc,c,why))
    ranked.sort(key=lambda z:z[0],reverse=True)
    for sc,c,why in ranked[:10]:
        if sc<MIN_ALERT: continue
        key=(c['token'] or c['pool']).lower(); now=time.time(); prev=seen.get(key)
        if prev and now-prev['time']<1800 and sc<prev['score']+5: continue
        amt=min(MAX_POSITION,WALLET*(.25 if sc>=97 else .20 if sc>=94 else .15)); e1,e2=c['mc']*.97,c['mc']*1.025; stop=c['mc']*.84; t1,t2,t3=c['mc']*1.35,c['mc']*1.65,c['mc']*2
        verdict='ENTER NOW' if sc>=95 and c['p5']<=15 else 'BUY RETEST'
        await tg(s,f"🚨 RH GEM HUNTER — {sc}/100\n\n{c['name']}\nContract: {c['token']}\nMC: {money(c['mc'])} | Liquidity: {money(c['liq'])}\n5m Vol: {money(c['vol5'])} | 1h Vol: {money(c['vol1h'])}\n5m Buys/Sells: {c['b5']}/{c['s5']}\n5m: {c['p5']:+.1f}% | 15m: {c['p15']:+.1f}%\nAge: {c['age']:.0f} min\n\nSuggested amount: ${amt:.0f}\nEntry MC: {money(e1)}–{money(e2)}\nHard invalidation: {money(stop)}\nTP1: {money(t1)} → 30%\nTP2: {money(t2)} → 30%\nTP3: {money(t3)} → 25%\nRunner: 15%\n\nWhy: {', '.join(why[:5])}\nVERDICT: {verdict}\n\n⚠️ Public enrichment may lag. No profit is guaranteed.")
        seen[key]={'time':now,'score':sc}
    print(datetime.now().isoformat(timespec='seconds'),'pools',len(pools),'tracked',len(ranked))
async def main():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
        await tg(s,'✅ Robinhood 24/7 Gem Hunter started.')
        while True:
            try: await scan(s)
            except Exception as e: print('scan error',repr(e))
            await asyncio.sleep(SCAN_INTERVAL)
if __name__=='__main__': asyncio.run(main())
