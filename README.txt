GEM HUNTER V2.1 — SAFETY GATE

Replace the files in your existing GitHub repo with these files.

New Railway variables:
SAFETY_FAIL_CLOSED=true
MAX_BUY_TAX=0.10
MAX_SELL_TAX=0.10
MAX_TOP_HOLDER_PCT=20
GOPLUS_ACCESS_TOKEN=   (optional/depends on your GoPlus plan; keep secret)

Behavior:
- BSC: GoPlus token security hard gate.
- Solana: GoPlus Solana token security hard gate.
- Robinhood: basic on-chain contract check, but ENTER is blocked while full sellability
  remains unverified. It may still send WATCH.
- Safety FAIL: silently rejected.
- Safety UNKNOWN: WATCH only; never ENTER.
- Safety PASS + score >= ENTER_SCORE + not overextended: ENTER — SAFETY PASSED.

This reduces known rug/honeypot risks but cannot guarantee profit or eliminate all scams.
