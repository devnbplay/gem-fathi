import os, asyncio, time
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
NETWORKS = [x.strip() for x in os.getenv("NETWORKS", "robinhood,solana,bsc").split(",") if x.strip()]
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "20"))
MIN_MC = float(os.getenv("MIN_MC", "100000"))
MAX_MC = float(os.getenv("MAX_MC", "1200000"))
MIN_LIQ = float(os.getenv("MIN_LIQ", "25000"))
MIN_TRACK = int(os.getenv("MIN_TRACK_SCORE", "65"))
MIN_ALERT = int(os.getenv("MIN_ALERT_SCORE", "78"))
ENTER_SCORE = int(os.getenv("ENTER_SCORE", "88"))
WALLET = float(os.getenv("WALLET_USD", "400"))
MAX_POSITION = float(os.getenv("MAX_POSITION_USD", "100"))
GOPLUS_TOKEN = os.getenv("GOPLUS_ACCESS_TOKEN", "").strip()
FAIL_CLOSED = os.getenv("SAFETY_FAIL_CLOSED", "true").lower() == "true"
MAX_BUY_TAX = float(os.getenv("MAX_BUY_TAX", "0.10"))
MAX_SELL_TAX = float(os.getenv("MAX_SELL_TAX", "0.10"))
MAX_TOP_HOLDER = float(os.getenv("MAX_TOP_HOLDER_PCT", "20"))
MAX_ENTER_P5 = float(os.getenv("MAX_ENTER_P5", "12"))
MAX_ENTER_P15 = float(os.getenv("MAX_ENTER_P15", "35"))
MAX_VOL5_MC_RATIO = float(os.getenv("MAX_VOL5_MC_RATIO", "0.75"))
MAX_TX5 = int(os.getenv("MAX_TX5", "1800"))

GT = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept":"application/json;version=20230203","User-Agent":"Fast-Gem-Hunter/2.0"}
seen = {}
history = {}

def num(x, d=0.0):
    try: return float(x) if x not in (None, "") else d
    except: return d

def money(x):
    if x >= 1_000_000: return f"${x/1_000_000:.2f}M"
    if x >= 1000: return f"${x/1000:.1f}K"
    return f"${x:.0f}"

async def tg(s, text):
    if not TG_TOKEN or not TG_CHAT:
        print(text); return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    async with s.post(url, json={
        "chat_id": TG_CHAT, "text": text,
        "disable_web_page_preview": True
    }, timeout=15) as r:
        if r.status >= 300:
            print("Telegram error", r.status, await r.text())

async def gt(s, network, endpoint):
    url = f"{GT}/networks/{network}/{endpoint}"
    async with s.get(url, headers=HEADERS, params={"page":1}, timeout=20) as r:
        if r.status == 429:
            print("rate limited", network, endpoint)
            return []
        r.raise_for_status()
        return (await r.json()).get("data", [])

def parse_pool(item, network):
    a = item.get("attributes", {}) or {}
    rel = item.get("relationships", {}) or {}
    tx = a.get("transactions", {}) or {}
    vol = a.get("volume_usd", {}) or {}
    pc = a.get("price_change_percentage", {}) or {}
    def t(w): return tx.get(w, {}) or {}

    base = (((rel.get("base_token") or {}).get("data") or {}).get("id") or "")
    token = base.split("_", 1)[-1] if "_" in base else base
    created = a.get("pool_created_at")
    age = 999999
    if created:
        try:
            age = max(0, (datetime.now(timezone.utc) -
                datetime.fromisoformat(created.replace("Z","+00:00"))).total_seconds()/60)
        except: pass

    return {
        "network":network, "name":a.get("name") or "UNKNOWN",
        "token":token, "pool":a.get("address") or "",
        "mc":num(a.get("market_cap_usd")) or num(a.get("fdv_usd")),
        "liq":num(a.get("reserve_in_usd")),
        "vol5":num(vol.get("m5")), "vol1h":num(vol.get("h1")),
        "b5":int(num(t("m5").get("buys"))), "s5":int(num(t("m5").get("sells"))),
        "b15":int(num(t("m15").get("buys"))), "s15":int(num(t("m15").get("sells"))),
        "p5":num(pc.get("m5")), "p15":num(pc.get("m15")), "age":age
    }

def score(c):
    if c["mc"] <= 0 or c["liq"] < MIN_LIQ or c["mc"] < 50_000 or c["mc"] > 2_000_000:
        return 0, ["outside universe/thin liquidity"]

    s, why = 0, []
    if MIN_MC <= c["mc"] <= MAX_MC:
        s += 18; why.append("good MC")
    elif 75_000 <= c["mc"] <= 1_500_000:
        s += 9

    lr = c["liq"] / max(c["mc"], 1)
    if .08 <= lr <= .50:
        s += 15; why.append("healthy liquidity")
    elif lr >= .05: s += 8
    else: s -= 18

    t5, t15 = c["b5"]+c["s5"], c["b15"]+c["s15"]
    br = c["b5"] / max(c["s5"], 1)

    if t5 >= 20:
        s += 12; why.append("fast activity")
    elif t5 >= 8: s += 6

    if br >= 1.8 and c["b5"] >= 8:
        s += 15; why.append("buyers dominate")
    elif br >= 1.3: s += 7

    if t15 and (t5/5) >= (t15/15)*1.35:
        s += 12; why.append("transactions accelerating")

    if c["vol5"] >= 10_000:
        s += 10; why.append("volume accelerating")
    elif c["vol5"] >= 3_500: s += 5

    # Earlier is better: reward momentum before a giant candle.
    if 0.5 <= c["p5"] <= 12:
        s += 12; why.append("early momentum")
    elif 12 < c["p5"] <= 22:
        s += 5
    elif c["p5"] > 35:
        s -= 22; why.append("already extended")

    if 1 <= c["p15"] <= 30: s += 5
    elif c["p15"] > 70: s -= 12

    if 1 <= c["age"] <= 120:
        s += 6; why.append("fresh")
    elif c["age"] <= 360: s += 2

    # Local acceleration memory: rewards a token whose activity is improving
    key = (c["network"], (c["token"] or c["pool"]).lower())
    old = history.get(key)
    if old:
        dt = max(time.time()-old["time"], 1)
        if c["b5"] > old["b5"] and c["vol5"] > old["vol5"]:
            s += 6; why.append("activity rising now")
        if c["p5"] > old["p5"] and c["p5"] <= 15:
            s += 3
    history[key] = {"time":time.time(),"b5":c["b5"],"vol5":c["vol5"],"p5":c["p5"]}

    return max(0, min(100, s)), why

async def discover_network(s, network):
    # To respect the public API limit, new pools are the priority.
    # Trending is sampled less often by the main loop.
    out = {}
    for x in await gt(s, network, "new_pools"):
        out[x.get("id")] = x
    return list(out.values())

async def scan_network(s, network, include_trending=False):
    out = {}
    for x in await discover_network(s, network):
        out[x.get("id")] = x
    if include_trending:
        for x in await gt(s, network, "trending_pools"):
            out[x.get("id")] = x

    ranked = []
    for x in out.values():
        c = parse_pool(x, network)
        sc, why = score(c)
        if sc >= MIN_TRACK:
            ranked.append((sc,c,why))
    ranked.sort(key=lambda z:z[0], reverse=True)
    return ranked


def truthy(v):
    return str(v).lower() in ("1","true","yes")

def pct(v):
    x = num(v, 0.0)
    return x * 100 if x <= 1 else x

def security_headers():
    h = {"Accept":"application/json"}
    if GOPLUS_TOKEN:
        h["Authorization"] = f"Bearer {GOPLUS_TOKEN}"
    return h

async def security_check(s, c):
    """Hard safety gate. UNKNOWN is never allowed to become ENTER when fail-closed."""
    net, token = c["network"], c["token"]
    result = {"status":"UNKNOWN", "reasons":[], "warnings":[], "source":""}

    if not token:
        result["reasons"].append("missing token address")
        return result

    # Market-level hard gates apply on every chain.
    if c["liq"] <= 0:
        return {"status":"FAIL","reasons":["zero liquidity"],"warnings":[],"source":"market"}
    if c["liq"] < MIN_LIQ:
        return {"status":"FAIL","reasons":["liquidity below minimum"],"warnings":[],"source":"market"}
    if c["b5"] > 0 and c["s5"] == 0 and c["b5"] >= 12:
        result["warnings"].append("buys seen but no sells in 5m")

    try:
        if net == "bsc":
            url = "https://api.gopluslabs.io/api/v1/token_security/56"
            async with s.get(url, params={"contract_addresses":token.lower()},
                             headers=security_headers(), timeout=12) as r:
                if r.status != 200:
                    result["reasons"].append(f"GoPlus unavailable ({r.status})")
                    return result
                js = await r.json()
            d = (js.get("result") or {}).get(token.lower())
            if not d:
                result["reasons"].append("no BSC security result")
                return result
            result["source"] = "GoPlus"

            hard = {
                "is_honeypot":"honeypot",
                "is_blacklisted":"blacklist control",
                "transfer_pausable":"transfers can be paused",
                "can_take_back_ownership":"ownership can be reclaimed",
            }
            for k,label in hard.items():
                if truthy(d.get(k)): result["reasons"].append(label)
            if truthy(d.get("cannot_sell_all")):
                result["reasons"].append("cannot sell all")
            if truthy(d.get("is_mintable")):
                result["reasons"].append("mintable supply")
            if truthy(d.get("slippage_modifiable")):
                result["reasons"].append("modifiable trading tax/slippage")
            if pct(d.get("buy_tax")) > MAX_BUY_TAX*100:
                result["reasons"].append(f"buy tax {pct(d.get('buy_tax')):.1f}%")
            if pct(d.get("sell_tax")) > MAX_SELL_TAX*100:
                result["reasons"].append(f"sell tax {pct(d.get('sell_tax')):.1f}%")
            if d.get("is_in_dex") == "0":
                result["reasons"].append("not detected on DEX")

            holders = d.get("holders") or []
            if holders:
                top = max((pct(h.get("percent")) for h in holders), default=0)
                if top > MAX_TOP_HOLDER:
                    result["reasons"].append(f"top holder {top:.1f}%")
            if result["reasons"]:
                result["status"] = "FAIL"
            else:
                result["status"] = "PASS"
            return result

        if net == "solana":
            url = "https://api.gopluslabs.io/api/v1/solana/token_security"
            async with s.get(url, params={"contract_addresses":token},
                             headers=security_headers(), timeout=12) as r:
                if r.status != 200:
                    result["reasons"].append(f"Solana security unavailable ({r.status})")
                    return result
                js = await r.json()
            raw = js.get("result") or {}
            d = raw.get(token) if isinstance(raw, dict) else None
            if d is None and isinstance(raw, dict) and len(raw) == 1:
                d = next(iter(raw.values()))
            if not isinstance(d, dict):
                result["reasons"].append("no Solana security result")
                return result
            result["source"] = "GoPlus"

            # Fail on dangerous authorities/controls when the provider reports them.
            danger_keys = {
                "mintable":"mint authority active",
                "is_mintable":"mint authority active",
                "freezable":"freeze authority active",
                "is_freezable":"freeze authority active",
                "closable":"token can be closed",
                "non_transferable":"non-transferable token",
                "transfer_fee_upgradable":"transfer fee can be changed",
            }
            for k,label in danger_keys.items():
                if truthy(d.get(k)): result["reasons"].append(label)

            # Common nested authority fields.
            for k in ("mint_authority","freeze_authority"):
                v = d.get(k)
                if v not in (None, "", "null", False, "0"):
                    result["reasons"].append(f"{k.replace('_',' ')} present")

            holders = d.get("holders") or d.get("holder_info") or []
            if isinstance(holders, list) and holders:
                vals=[]
                for h in holders:
                    if isinstance(h, dict):
                        vals.append(pct(h.get("percent", h.get("percentage", 0))))
                if vals and max(vals) > MAX_TOP_HOLDER:
                    result["reasons"].append(f"top holder {max(vals):.1f}%")

            result["status"] = "FAIL" if result["reasons"] else "PASS"
            return result

        if net == "robinhood":
            # Robinhood Chain is EVM-compatible, but GoPlus does not currently list
            # chain 4663 in its supported-chain set. Do a basic contract-code check,
            # then fail closed for ENTER because sellability is not independently verified.
            rpc = "https://rpc.mainnet.chain.robinhood.com"
            payload = {"jsonrpc":"2.0","id":1,"method":"eth_getCode","params":[token,"latest"]}
            async with s.post(rpc, json=payload, timeout=10) as r:
                if r.status != 200:
                    result["reasons"].append("Robinhood RPC unavailable")
                    return result
                js = await r.json()
            bytecode = js.get("result","0x")
            if bytecode in ("0x","0x0",None):
                return {"status":"FAIL","reasons":["no token contract bytecode"],"warnings":[],
                        "source":"Robinhood RPC"}
            result["source"] = "Robinhood RPC"
            result["reasons"].append("sellability/honeypot not independently verified")
            return result

        result["reasons"].append("unsupported safety network")
        return result
    except Exception as e:
        result["reasons"].append("security provider error")
        return result



def entry_quality(c):
    """Reject obvious vertical-pump/chase structures before ENTER."""
    reasons = []
    tx5 = c["b5"] + c["s5"]
    if c["p5"] > MAX_ENTER_P5:
        reasons.append(f"5m move already +{c['p5']:.1f}%")
    if c["p15"] > MAX_ENTER_P15:
        reasons.append(f"15m move already +{c['p15']:.1f}%")
    if c["mc"] > 0 and c["vol5"] / c["mc"] > MAX_VOL5_MC_RATIO:
        reasons.append("abnormal 5m volume vs market cap")
    if tx5 > MAX_TX5:
        reasons.append("extreme transaction burst")
    if c["age"] <= 3 and c["p5"] > 8:
        reasons.append("very fresh token already vertical")
    # If the market feed first sees an enormous valuation with a tiny age,
    # don't chase even when the short-window % field understates the launch candle.
    if c["age"] <= 10 and c["mc"] >= 500_000 and c["p15"] >= 20:
        reasons.append("large valuation reached too quickly")
    return (len(reasons) == 0), reasons


async def maybe_alert(s, sc, c, why):
    if sc < MIN_ALERT:
        return

    key = (c["network"], (c["token"] or c["pool"]).lower())
    now = time.time()
    prev = seen.get(key)
    if prev and now-prev["time"] < 1200 and sc < prev["score"]+5:
        return

    safety = await security_check(s, c)

    # A confirmed safety failure never becomes a gem/entry alert.
    if safety["status"] == "FAIL":
        print("REJECT", c["name"], "; ".join(safety["reasons"]))
        seen[key] = {"time":now,"score":sc}
        return

    quality_ok, quality_reasons = entry_quality(c)
    can_enter = (safety["status"] == "PASS" and quality_ok)
    if sc >= ENTER_SCORE and can_enter:
        verdict = "🚨 ENTER — SAFETY + ENTRY PASSED"
    elif sc >= MIN_ALERT:
        verdict = "👀 WATCH — NO ENTRY YET"
    else:
        return

    risk_amt = .12 if not can_enter else (.18 if sc < 93 else .22)
    amt = min(MAX_POSITION, WALLET*risk_amt)
    stop = c["mc"]*.84
    t1, t2, t3 = c["mc"]*1.25, c["mc"]*1.50, c["mc"]*2.0

    if safety["status"] == "PASS":
        safety_line = f"🛡 Safety: PASS ({safety['source']})"
    else:
        safety_line = "🟠 Safety: UNKNOWN — ENTRY BLOCKED"

    if quality_ok:
        quality_line = "📈 Entry quality: PASS"
    else:
        quality_line = "⛔ Entry quality: FAIL — " + ", ".join(quality_reasons[:3])

    if can_enter:
        action = "Automated safety + anti-pump + momentum gates passed. Still high risk; use the invalidation."
    elif not quality_ok:
        action = "DO NOT ENTER NOW. Vertical/extended structure detected."
    else:
        action = "DO NOT ENTER. Safety/sellability could not be verified."

    extra = safety["reasons"] + safety["warnings"]
    extra_line = ("Safety note: " + ", ".join(extra[:4])) if extra else ""

    text = (
        f"{verdict} — {sc}/100\n\n"
        f"{c['name']}\n"
        f"Contract: {c['token']}\n"
        f"MC: {money(c['mc'])} | Liq: {money(c['liq'])}\n"
        f"5m Vol: {money(c['vol5'])} | Buys/Sells: {c['b5']}/{c['s5']}\n"
        f"5m: {c['p5']:+.1f}% | 15m: {c['p15']:+.1f}% | Age: {c['age']:.0f}m\n\n"
        f"{safety_line}\n"
        f"{quality_line}\n"
        f"{extra_line}\n\n"
        f"Size cap: ${amt:.0f}\n"
        f"Invalidation MC: {money(stop)}\n"
        f"TP1: {money(t1)} (+25%)\n"
        f"TP2: {money(t2)} (+50%)\n"
        f"TP3: {money(t3)} (+100%)\n\n"
        f"Why: {', '.join(why[:6])}\n"
        f"{action}\n"
        "⚠️ No automated checker can guarantee a token cannot rug or that a trade will profit."
    )
    await tg(s, text)
    seen[key] = {"time":now,"score":sc}

async def main():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
        await tg(s, "⚡ Fast Multi-Chain Gem Hunter V2 started.")
        cycle = 0
        while True:
            cycle += 1
            # One network per cycle keeps public API usage under control.
            network = NETWORKS[(cycle-1) % len(NETWORKS)]
            # Fresh-pool priority: one API request each cycle. With 3 chains and
            # 20-second cycles, every chain is checked once per minute.
            include_trending = False
            try:
                ranked = await scan_network(s, network, include_trending)
                for sc,c,why in ranked[:8]:
                    await maybe_alert(s, sc,c,why)
                print(datetime.now().isoformat(timespec="seconds"),
                      network, "tracked", len(ranked))
            except Exception as e:
                print("scan error", network, repr(e))
            await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
