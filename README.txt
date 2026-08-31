GEM HUNTER V2.2 — SAFETY + ANTI-PUMP + MULTI-CHAIN ROTATION

Upload these files over the existing GitHub repository.

Important Railway variable:
NETWORKS=robinhood,solana,bsc

New anti-pump variables:
MAX_ENTER_P5=12
MAX_ENTER_P15=35
MAX_VOL5_MC_RATIO=0.75
MAX_TX5=1800

ENTER now requires:
1. Security gate PASS
2. Entry-quality/anti-pump PASS
3. Momentum score >= ENTER_SCORE

Vertical launch pumps become WATCH/NO ENTRY rather than ENTER.

Multi-chain:
The scanner rotates robinhood -> solana -> bsc, prioritizing new pools and keeping
public API request volume controlled. It does not include the chain name in Telegram alerts.

NOTE:
Seeing mostly Solana can also reflect the upstream new-pool feed having far more qualifying
Solana pools than BSC/Robinhood. This version guarantees rotation, not equal alert counts.

No automated checker can guarantee profit or detect every rug.
