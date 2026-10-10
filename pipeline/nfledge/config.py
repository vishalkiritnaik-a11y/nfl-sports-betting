"""Central configuration. Everything overridable by environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("NFLEDGE_CACHE", ROOT / ".cache"))
OUT_DIR = Path(os.environ.get("NFLEDGE_OUT", ROOT / "web" / "public" / "data"))
DB_PATH = Path(os.environ.get("NFLEDGE_DB", ROOT / "data" / "nfledge.sqlite"))

NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"

# Seasons
PBP_FIRST_SEASON = 2016          # play-by-play used for team features
PLAYER_FIRST_SEASON = 2019       # player stats / snap counts used for TD model
BACKTEST_FIRST_SEASON = 2021     # first season of walk-forward evaluation
HISTORY_SEASONS_IN_UI = int(os.environ.get("NFLEDGE_UI_HISTORY", 2))  # past seasons shipped to UI

MODEL_VERSION = "game-v1.0+td-v1.0"

# Value thresholds (percentage points over the margin-adjusted market probability)
DEFAULT_MIN_EDGE_PP = float(os.environ.get("NFLEDGE_MIN_EDGE_PP", 3.0))

# Optional secrets (server-side only; read in GitHub Actions)
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "").strip()
ODDS_API_REGIONS = os.environ.get("ODDS_API_REGIONS", "us")
ODDS_API_TD_PROPS = os.environ.get("ODDS_API_TD_PROPS", "0") == "1"  # paid tier only

# Ties: NFL regular-season ties are rare (~0.3% of games 2012+). Win probabilities
# shown are conditional on a decisive result and therefore sum to 100%.
TIE_RATE_NOTE = "Ties excluded (historically ~0.3% of games); probabilities are conditional on a decisive result."
