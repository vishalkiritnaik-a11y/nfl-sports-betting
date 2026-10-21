// Data contracts produced by pipeline/nfledge/build.py. Keep in sync with docs/DATA_CONTRACTS.md.

export interface TeamInfo {
  abbr: string; name: string; nick: string; conf: string; division: string;
  color: string; color2: string; logo: string;
}

export interface WeekRef {
  season: number; week: number; file: string; games: number;
  kind: "current" | "past" | "lookahead"; label: string;
}

export interface Source { file: string; url: string; source_updated?: string | null; fetched?: string | null }

export interface Meta {
  generated: string; season: number; current_week: number; model_version: string;
  weeks: WeekRef[]; teams: Record<string, TeamInfo>; default_min_edge_pp: number;
  odds_source: string; odds_error?: string | null; td_market_available: boolean; weather_enabled: boolean;
  sources: Source[]; features: { live: string[]; unavailable: string[] };
  methodology: {
    game: { trained_on: string; n_train: number; sigma_margin: number; sigma_total: number;
      coefficients: { feature: string; label: string; pts_per_sd: number; logit_per_sd: number; sd: number }[] };
    td: { rates_per_opportunity: Record<string, number>; calibration: Record<string, number>; n_calibration: number;
      team_opportunity_model: Record<string, number[]> };
  };
  build_seconds: number;
  retrain?: Retrain | null;
}
export interface RetrainScore { n: number; log_loss: number; accuracy: number; margin_mae: number; total_mae: number }
export interface RetrainCfg { rating: { k_mult: number; prior_regress: number }; model: { alpha: number; logit_c: number; half_life: number | null };
  prior: RetrainScore; current: RetrainScore }
export interface Retrain {
  season: number; trained_through_week: number; for_week: number; generated: string; version: string; changed: boolean; rule: string;
  incumbent: RetrainCfg; chosen: RetrainCfg; games_in_training: number; grid_top: RetrainCfg[];
  weekly_current_season: { week: number; games: number; model_correct: number; market_correct: number; model_log_loss: number; market_log_loss: number | null }[];
  history: { for_week: string; generated: string; version: string; changed: boolean; prior_log_loss: number; current_log_loss: number }[];
}

export interface Contribution { feature: string; label: string; value: number; points: number }

export interface Distribution {
  margin_sd: number; total_sd: number; margin_hist: { lo: number; hi: number; p: number }[];
  margin_p10_p90: [number, number]; total_p10_p90: [number, number];
  p_home_cover?: number; p_over?: number;
}

export interface Prediction {
  p_home: number; p_away: number; p_margin_model: number; p_logit_model: number; elo_prob: number;
  exp_margin: number; exp_total: number; home_pts: number; away_pts: number;
  exp_total_weather_adj?: number; weather_total_delta?: number; exp_total_base?: number; weather_applied?: boolean;
  distribution: Distribution; contributions: Contribution[]; total_contributions: Contribution[];
  baseline_margin: number; baseline_total: number;
  tie_note: string; model_version: string; trained_on: string; backtest: boolean;
}

export interface Market {
  source: string; book?: string; snapshot?: string | null;
  home_moneyline?: number | null; away_moneyline?: number | null; spread_line?: number | null;
  home_spread_odds?: number | null; away_spread_odds?: number | null; total_line?: number | null;
  over_odds?: number | null; under_odds?: number | null;
  home_raw_implied?: number; away_raw_implied?: number; home_no_vig?: number; away_no_vig?: number; overround?: number;
  home_ml_book?: string; away_ml_book?: string;
}

export interface ValueRow {
  market: "moneyline" | "spread" | "total"; selection: string; team: string | null; model_p: number;
  odds: number; decimal: number; raw_implied: number; no_vig: number; overround: number;
  edge_pp: number; edge_vs_raw_pp: number; ev_per_unit: number; roi_pct: number;
  anchored_p?: number; raw_edge_pp?: number; raw_ev_per_unit?: number;
}

export interface Injury {
  player_id: string; name: string; position: string; group: string; status: string; designated: boolean;
  practice: string; injury: string | null;
}

export interface FormWindow {
  games: number; spans_prior_season: boolean; epa_play: number; def_epa_play: number;
  points_pg: number; points_allowed_pg: number; success: number; record: string;
}

export interface Side {
  team: string; record: string; elo: number;
  qb: { id: string | null; name: string | null; epa_db: number; dropbacks: number; changed: boolean };
  rest_days: number; travel_km: number; tz_shift: number;
  season?: Record<string, number | null>; blended?: Record<string, number>;
  form?: Record<string, FormWindow>; injuries?: Injury[];
}

export interface Weather {
  status: "forecast" | "observed" | "indoor" | "unavailable" | "beyond_forecast_range";
  roof?: string | null; roof_type?: string | null; roof_note?: string; source?: string; lead_hours?: number;
  temp_f?: number | null; humidity_pct?: number; wind_mph?: number | null; gust_mph?: number;
  precip_prob_pct?: number; precip_in?: number; snow_in?: number; wind_range_mph?: [number, number];
  temp_range_f?: [number, number]; fetched?: string; error?: string; wind_kickoff_mph?: number;
}

export interface Scenario {
  name: string; kind: "qb" | "weather"; team?: string; trigger_status?: string | null;
  p_home: number; exp_margin: number; exp_total: number; delta_p_team?: number; delta_total?: number;
}

export interface MatchupRow {
  key: string; label: string; off_value: number; off_rank: number; off_n: number; def_value: number;
  def_rank: number; def_n: number; edge_z: number; verdict: string; kind: string;
}

export interface H2H {
  game_id: string; season: number; week: number; gameday: string; home: string; away: string;
  home_score: number; away_score: number; total: number; home_qb: string; away_qb: string;
  home_coach: string; away_coach: string; same_qbs: number; same_coaches: number; relevance: string;
}

export interface Confidence { label: "High" | "Medium" | "Low" | "n/a"; base?: "High" | "Medium" | "Low"; score?: number; base_score?: number; reasons: string[] }

export interface RecWhy { factor: string; points: number; text: string }
export interface Rec {
  market: "spread" | "moneyline" | "total"; side: string; label: string; line: number | null; odds: number;
  score: number; verdict: "Bet" | "Lean" | "Pass"; p_model: number; p_market: number; p_win: number; ev: number;
  other_score: number; why: RecWhy[];
}
export interface NoteItem { text: string; source: string; url?: string }
export interface GameRecs {
  markets: Partial<Record<"spread" | "moneyline" | "total", Rec>>;
  opening: { source: string; url?: string; home_ml?: number; away_ml?: number; spread_line?: number; total_line?: number } | null;
  notes: { updated?: string; items?: NoteItem[]; experts?: { market: string; side: string; source: string; url?: string }[] } | null;
}
export interface RecPick {
  game_id: string; matchup: string; kickoff_utc: string; season: number; week: number; market: "spread" | "moneyline" | "total";
  side: string; label: string; line: number | null; odds: number; score: number; verdict: "Bet" | "Lean" | "Pass"; p_win: number;
  result: "won" | "lost" | "push" | "pending"; profit: number; final: string | null;
  flagged_at?: string | null; clv?: number | null;
}

export interface Game {
  game_id: string; season: number; week: number; game_type: string; gameday: string; weekday: string;
  gametime_et: string; kickoff_utc: string; location: string; div_game: boolean;
  venue: { stadium: string; surface: string | null; roof: string | null; name?: string; roof_type?: string; elevation_m?: number };
  lookahead: boolean; home: Side; away: Side; prediction: Prediction; market: Market | null; values: ValueRow[];
  result?: { home_score: number; away_score: number; winner: string; model_correct: boolean | null };
  recs?: GameRecs;
  confidence: Confidence; factors: { home: string[]; away: string[]; risks?: string[] };
  weather?: Weather; scenarios?: Scenario[]; h2h?: H2H[];
  matchups?: { home_off: MatchupRow[]; away_off: MatchupRow[]; home_extras: Record<string, number>;
    away_extras: Record<string, number>; unavailable: string[]; note: string };
  history?: { run_id: string; p_home: number; exp_margin: number; exp_total: number; market_p_home: number | null }[];
  td_ruled_out?: { player_id: string; name: string; position: string; team: string }[];
}

export interface TDPlayer {
  player_id: string; name: string; headshot?: string | null; team: string; opp: string; position: string;
  game_id: string; status: string; p: number; p_if_uncertain_out?: number | null; p_raw_poisson?: number;
  lam_rush: number; lam_rec: number; rush_share_of_td?: number; p_first_td_approx?: number;
  exp_opps?: Record<string, number>; shares?: Record<string, number>; usage?: Record<string, number>;
  finishing_mult?: number; opp_mult?: { rush: number; rec: number }; team_exp_points?: number; team_exp_margin?: number;
  season?: { games?: number; carries_pg?: number; targets_pg?: number; receptions_pg?: number; rush_yds_pg?: number;
    rec_yds_pg?: number; season_tds?: number; target_share?: number | null };
  recent?: { last3: number; last5: number; last10: number; season_i5_carries: number; season_i10_carries: number;
    season_rz_targets: number; season_ez_targets: number; season_tds: number };
  snap_pct_last3?: number[]; opp_vs_pos?: { td_pg: number; rank: number; games: number } | null;
  confidence?: Confidence; why?: string;
  market?: { odds: number; book: string; raw_implied: number; edge_pp: number; ev_per_unit: number; roi_pct: number; note: string } | null;
  scored?: number | null; backtest?: boolean; touches?: number | null; logged_at?: string; graded_from?: string | null;
}

export interface WeekData { season: number; week: number; generated: string; is_current: boolean; games: Game[]; td: TDPlayer[] }

export interface Scores { n: number; log_loss: number; brier: number; accuracy: number | null; auc: number | null }
export interface CalBin { lo: number; hi: number; n: number; pred: number; obs: number; ci90: [number, number] }

export interface Performance {
  game: {
    period: string; method: string;
    overall: Record<"model" | "logit_component" | "margin_component" | "elo" | "market" | "model_same_games", Scores>;
    by_season: { season: number; model: Scores; elo: Scores; market: Scores | null; model_same_games: Scores | null }[];
    current_season_by_week: (Scores & { week: number; correct: number })[];
    segments: (Scores & { segment: string })[]; calibration: CalBin[];
    margin_mae: number; market_spread_mae: number; total_mae: number; market_total_mae: number;
    corr_with_market: number; ties_excluded: number;
    betting: { market: string; min_edge_pp: number; bets: number; pushes: number; wins: number; win_rate: number | null;
      units: number; roi_pct: number | null; win_rate_ci90: [number, number] | null }[];
    betting_note: string;
  };
  td: {
    period: string; method: string; overall: Scores & { base_rate: number; base_rate_log_loss: number };
    calibration: CalBin[];
    by_position: (Scores & { position: string; pred_mean: number; obs_mean: number; calibration: CalBin[] })[];
    by_season: (Scores & { season: number })[];
    top_picks: { rule: string; n: number; hit_rate: number | null; avg_pred: number | null }[];
    market_note: string;
  };
  prospective: {
    games_logged: number; games_graded: number; td_logged: number; td_graded: number; since: string | null;
    game_scores?: Scores; market_scores?: Scores; model_same_games?: Scores; td_scores?: Scores; td_calibration?: CalBin[];
    recent: { game_id: string; run_id: string; p_home: number; market_p_home: number | null; home_team: string;
      away_team: string; home_score: number | null; away_score: number | null; confidence: string }[];
  };
  disclaimer: string;
  tiers?: {
    td: Record<"prior" | "current", Record<string, TierStat>>;
    game: Record<"prior" | "current", Record<string, TierStat>>;
    td_scores?: Record<"prior" | "current", Record<string, TierStat>>;
  };
}

export interface TierStat { n: number; pred: number | null; hit: number | null; band: string }

export interface GamePick {
  game_id: string; matchup: string; kickoff_utc: string; logged_at: string; season: number; week: number;
  market: "moneyline" | "spread" | "total"; selection: string; side: string; line: number | null; odds: number;
  model_p: number; no_vig: number; edge_pp: number; ev: number; price_source: string;
  anchored_p: number; anchored_edge_pp: number; anchored_ev: number;
  result: "won" | "lost" | "push" | "pending"; profit: number; final: string | null;
}
export interface TDPick {
  game_id: string; season: number; week: number; kickoff_utc: string; logged_at: string; player_id: string; name: string;
  team: string; position: string; p: number; score: number; status: string | null; odds: number | null;
  result: "won" | "lost" | "void" | "pending";
}
export interface Picks { generated: string; game: GamePick[]; td: TDPick[]; recs?: RecPick[]; anchor?: Record<string, Record<string, { b: number; b_ci90: [number, number]; n: number }>> }

export interface TeaserRate { n: number; hit: number | null }
export interface TeaserStats {
  generated: string; tease: number; fav_range: [number, number]; dog_range: [number, number];
  periods: { all: { from: number; to: number }; recent: { from: number; to: number } };
  all: { fav: TeaserRate; dog: TeaserRate; both: TeaserRate };
  recent: { fav: TeaserRate; dog: TeaserRate; both: TeaserRate };
  break_even: Record<string, number>;
}
