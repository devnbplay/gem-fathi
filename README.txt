FAST MULTI-CHAIN GEM HUNTER V2

Replace hunter.py in your GitHub repository with this version.

Railway variables to add/change:
NETWORKS=robinhood,solana,bsc
SCAN_INTERVAL_SECONDS=20
MIN_MC=100000
MAX_MC=1200000
MIN_LIQ=25000
MIN_TRACK_SCORE=65
MIN_ALERT_SCORE=78
ENTER_SCORE=88

Keep your existing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WALLET_USD and MAX_POSITION_USD.

IMPORTANT:
This version prioritizes fresh/new pools and acceleration and rotates networks to stay near the public GeckoTerminal rate limit.
It is faster in decision logic, but public indexer data can still be delayed. True sub-minute direct-chain monitoring requires dedicated WebSocket/RPC feeds and DEX-specific event decoding.
