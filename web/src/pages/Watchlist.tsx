import { Link, useLocation } from "react-router-dom";
import { useApp } from "../App";
import MatchupCard from "../components/MatchupCard";
import TDTable from "../components/TDTable";
import { Note, Section } from "../components/ui";
import { useSettings } from "../lib/store";

export default function Watchlist() {
  const { meta, week } = useApp();
  const { watch } = useSettings();
  const { search } = useLocation();
  const games = week!.games.filter((g) => watch.games.includes(g.game_id));
  const players = week!.td.filter((t) => watch.players.includes(t.player_id));
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">Watchlist</h1>
        <p className="text-muted text-sm">Star games and players anywhere to keep them here. Players stay starred from week to week. The list is saved in this browser only.</p>
      </div>
      <Section title={`Games (${games.length})`}>
        {games.length === 0 ? <Note>No starred games in this week. Use the star on any matchup on the <Link className="link" to={{ pathname: "/", search }}>slate</Link>.</Note> :
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">{games.map((g) => <MatchupCard key={g.game_id} g={g} teams={meta.teams} />)}</div>}
      </Section>
      <Section title={`Players (${players.length})`}>
        {players.length === 0 ? <Note>No starred players with projections this week. Star players on the <Link className="link" to={{ pathname: "/touchdowns", search }}>touchdowns</Link> page.</Note> :
          <TDTable rows={players} teams={meta.teams} />}
      </Section>
    </div>
  );
}
