"""
NBA Value Alert Bot - Bet Grader
=================================
Automatically grades bets using NBA API box scores.
Runs daily at 7AM ET to grade previous day's bets.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import time
import bet_logger

logger = logging.getLogger(__name__)

# Market to stat mapping
# Maps our market names to NBA API stat column names
MARKET_STAT_MAP = {
    # Standard markets
    'Points': 'PTS',
    'Rebounds': 'REB',
    'Assists': 'AST',
    'Threes': 'FG3M',
    'Blocks': 'BLK',
    'Steals': 'STL',
    # Combo markets
    'Blocks + Steals': ['BLK', 'STL'],
    'Points + Rebounds + Assists': ['PTS', 'REB', 'AST'],
    'Points + Rebounds': ['PTS', 'REB'],
    'Points + Assists': ['PTS', 'AST'],
    'Rebounds + Assists': ['REB', 'AST'],
    # Special markets
    'Double Double': 'DOUBLE_DOUBLE',
    'Triple Double': 'TRIPLE_DOUBLE',
    'First Basket': 'FIRST_BASKET',  # Requires play-by-play
    'First Team Basket': 'FIRST_TEAM_BASKET',  # Requires play-by-play
}

# Team name normalization (API names to common variations)
TEAM_NAME_MAP = {
    'Atlanta Hawks': ['Atlanta', 'Hawks', 'ATL'],
    'Boston Celtics': ['Boston', 'Celtics', 'BOS'],
    'Brooklyn Nets': ['Brooklyn', 'Nets', 'BKN'],
    'Charlotte Hornets': ['Charlotte', 'Hornets', 'CHA'],
    'Chicago Bulls': ['Chicago', 'Bulls', 'CHI'],
    'Cleveland Cavaliers': ['Cleveland', 'Cavaliers', 'Cavs', 'CLE'],
    'Dallas Mavericks': ['Dallas', 'Mavericks', 'Mavs', 'DAL'],
    'Denver Nuggets': ['Denver', 'Nuggets', 'DEN'],
    'Detroit Pistons': ['Detroit', 'Pistons', 'DET'],
    'Golden State Warriors': ['Golden State', 'Warriors', 'GSW', 'GS'],
    'Houston Rockets': ['Houston', 'Rockets', 'HOU'],
    'Indiana Pacers': ['Indiana', 'Pacers', 'IND'],
    'LA Clippers': ['LA Clippers', 'Clippers', 'LAC'],
    'Los Angeles Lakers': ['Los Angeles', 'LA Lakers', 'Lakers', 'LAL'],
    'Memphis Grizzlies': ['Memphis', 'Grizzlies', 'MEM'],
    'Miami Heat': ['Miami', 'Heat', 'MIA'],
    'Milwaukee Bucks': ['Milwaukee', 'Bucks', 'MIL'],
    'Minnesota Timberwolves': ['Minnesota', 'Timberwolves', 'Wolves', 'MIN'],
    'New Orleans Pelicans': ['New Orleans', 'Pelicans', 'NOP', 'NO'],
    'New York Knicks': ['New York', 'Knicks', 'NYK', 'NY'],
    'Oklahoma City Thunder': ['Oklahoma City', 'Thunder', 'OKC'],
    'Orlando Magic': ['Orlando', 'Magic', 'ORL'],
    'Philadelphia 76ers': ['Philadelphia', 'Sixers', '76ers', 'PHI'],
    'Phoenix Suns': ['Phoenix', 'Suns', 'PHX'],
    'Portland Trail Blazers': ['Portland', 'Trail Blazers', 'Blazers', 'POR'],
    'Sacramento Kings': ['Sacramento', 'Kings', 'SAC'],
    'San Antonio Spurs': ['San Antonio', 'Spurs', 'SAS', 'SA'],
    'Toronto Raptors': ['Toronto', 'Raptors', 'TOR'],
    'Utah Jazz': ['Utah', 'Jazz', 'UTA'],
    'Washington Wizards': ['Washington', 'Wizards', 'WAS'],
}


def get_games_for_date(date: str) -> List[Dict]:
    """
    Fetch all NBA games for a specific date using nba_api.
    date format: 'YYYY-MM-DD'
    Returns list of game info with game IDs.
    """
    try:
        from nba_api.stats.endpoints import scoreboardv2

        # Convert date format for NBA API (MM/DD/YYYY)
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        nba_date = date_obj.strftime('%m/%d/%Y')

        # Add delay to avoid rate limiting
        time.sleep(1)

        scoreboard = scoreboardv2.ScoreboardV2(game_date=nba_date)
        game_header = scoreboard.game_header.get_data_frame()

        games = []
        for _, row in game_header.iterrows():
            games.append({
                'game_id': row['GAME_ID'],
                'game_date': date,
                'home_team_id': row['HOME_TEAM_ID'],
                'away_team_id': row['VISITOR_TEAM_ID'],
                'game_status': row['GAME_STATUS_TEXT'],
            })

        logger.info(f"Found {len(games)} games for {date}")
        return games

    except Exception as e:
        logger.error(f"Error fetching games for {date}: {e}")
        return []


def get_box_score(game_id: str) -> Dict[str, Dict]:
    """
    Fetch box score for a specific game using nba_api.
    Returns dict mapping player names to their stats.
    Uses V3 endpoint for 2025-26 season and later.
    """
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv3

        # Add delay to avoid rate limiting
        time.sleep(0.6)

        box_score = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        player_stats_df = box_score.player_stats.get_data_frame()

        player_stats = {}
        for _, row in player_stats_df.iterrows():
            # V3 uses firstName + familyName instead of playerName
            first_name = row.get('firstName', '')
            family_name = row.get('familyName', '')
            player_name = f"{first_name} {family_name}".strip()
            if not player_name:
                continue

            # Get stats - V3 uses camelCase column names
            pts = row.get('points', 0) or 0
            reb = row.get('reboundsTotal', 0) or 0
            ast = row.get('assists', 0) or 0
            blk = row.get('blocks', 0) or 0
            stl = row.get('steals', 0) or 0
            fg3m = row.get('threePointersMade', 0) or 0
            minutes = row.get('minutes', '0:00')

            # Check for double-double
            categories_10plus = sum([
                pts >= 10,
                reb >= 10,
                ast >= 10,
                blk >= 10,
                stl >= 10
            ])

            stats = {
                'PTS': pts,
                'REB': reb,
                'AST': ast,
                'BLK': blk,
                'STL': stl,
                'FG3M': fg3m,
                'MIN': minutes,
                'DOUBLE_DOUBLE': categories_10plus >= 2,
                'TRIPLE_DOUBLE': categories_10plus >= 3,
                'TEAM_ABBREVIATION': row.get('teamTricode', ''),
            }

            player_stats[player_name] = stats

        logger.info(f"Got box score for game {game_id}: {len(player_stats)} players")
        return player_stats

    except Exception as e:
        logger.error(f"Error fetching box score for game {game_id}: {e}")
        return {}


def get_play_by_play(game_id: str) -> Optional[Dict]:
    """
    Fetch play-by-play for first basket bets using nba_api.
    Returns info about first basket scorer.
    """
    try:
        from nba_api.stats.endpoints import playbyplayv2

        # Add delay to avoid rate limiting
        time.sleep(0.6)

        pbp = playbyplayv2.PlayByPlayV2(game_id=game_id)
        pbp_df = pbp.play_by_play.get_data_frame()

        # Look for first made shot (EVENTMSGTYPE 1 = made shot)
        made_shots = pbp_df[pbp_df['EVENTMSGTYPE'] == 1]

        if not made_shots.empty:
            first_shot = made_shots.iloc[0]
            return {
                'first_scorer': first_shot.get('PLAYER1_NAME'),
                'first_scorer_team': first_shot.get('PLAYER1_TEAM_NICKNAME'),
            }

        return None

    except Exception as e:
        logger.error(f"Error fetching play-by-play for game {game_id}: {e}")
        return None


def normalize_player_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    # Remove suffixes like Jr., III, etc.
    name = name.replace(' Jr.', '').replace(' Jr', '')
    name = name.replace(' III', '').replace(' II', '').replace(' IV', '')
    name = name.strip()
    return name.lower()


def find_player_in_box_score(player_name: str, box_score: Dict[str, Dict]) -> Optional[Dict]:
    """Find a player in the box score, handling name variations."""
    normalized_target = normalize_player_name(player_name)

    for box_player, stats in box_score.items():
        if normalize_player_name(box_player) == normalized_target:
            return stats

    # Try partial match (first and last name)
    target_parts = normalized_target.split()
    if len(target_parts) >= 2:
        target_first = target_parts[0]
        target_last = target_parts[-1]

        for box_player, stats in box_score.items():
            box_parts = normalize_player_name(box_player).split()
            if len(box_parts) >= 2:
                if box_parts[0] == target_first and box_parts[-1] == target_last:
                    return stats

    return None


def grade_bet(bet: Dict, player_stats: Dict, first_basket_info: Dict = None) -> Tuple[str, float]:
    """
    Grade a single bet based on player stats.

    Returns:
        Tuple of (result, profit_loss)
        result: 'win', 'loss', 'push', 'void', 'dnp'
        profit_loss: Units won/lost (positive for win, negative for loss)
    """
    market = bet['market']
    side = bet['side']
    line = bet.get('line', 0) or 0
    odds = bet['best_odds']

    # Calculate potential profit from odds
    if odds > 0:
        profit_if_win = odds / 100  # e.g., +150 = 1.5 units profit
    else:
        profit_if_win = 100 / abs(odds)  # e.g., -150 = 0.67 units profit

    # Player didn't play
    if player_stats is None:
        return 'dnp', 0.0

    # Check if player played (has minutes)
    minutes = player_stats.get('MIN', '0:00')
    if minutes == '0:00' or minutes == 0 or minutes is None or minutes == '':
        return 'dnp', 0.0

    # Get the relevant stat
    stat_key = MARKET_STAT_MAP.get(market)

    if stat_key is None:
        logger.warning(f"Unknown market type: {market}")
        return 'void', 0.0

    # Handle combo stats
    if isinstance(stat_key, list):
        actual_value = sum(player_stats.get(k, 0) or 0 for k in stat_key)
    elif stat_key == 'DOUBLE_DOUBLE':
        actual_value = player_stats.get('DOUBLE_DOUBLE', False)
    elif stat_key == 'TRIPLE_DOUBLE':
        actual_value = player_stats.get('TRIPLE_DOUBLE', False)
    elif stat_key == 'FIRST_BASKET':
        # Special handling for first basket
        if first_basket_info is None:
            return 'void', 0.0
        player_name = bet['player']
        first_scorer = first_basket_info.get('first_scorer', '')
        if normalize_player_name(player_name) == normalize_player_name(first_scorer):
            actual_value = True
        else:
            actual_value = False
    elif stat_key == 'FIRST_TEAM_BASKET':
        # Would need team-specific first basket logic
        return 'void', 0.0
    else:
        actual_value = player_stats.get(stat_key, 0) or 0

    # Grade based on side (Over/Under or Yes/No)
    if side == 'Over':
        if actual_value > line:
            return 'win', profit_if_win
        elif actual_value < line:
            return 'loss', -1.0
        else:
            return 'push', 0.0

    elif side == 'Under':
        if actual_value < line:
            return 'win', profit_if_win
        elif actual_value > line:
            return 'loss', -1.0
        else:
            return 'push', 0.0

    elif side == 'Yes':
        if actual_value:
            return 'win', profit_if_win
        else:
            return 'loss', -1.0

    elif side == 'No':
        if not actual_value:
            return 'win', profit_if_win
        else:
            return 'loss', -1.0

    return 'void', 0.0


def match_game_by_teams(bet_game: str, box_score: Dict[str, Dict]) -> bool:
    """
    Match a bet's game string to box score by checking team abbreviations.
    bet_game format: "Away Team @ Home Team"
    """
    if not bet_game or '@' not in bet_game:
        return False

    parts = bet_game.split('@')
    if len(parts) != 2:
        return False

    away_team = parts[0].strip().lower()
    home_team = parts[1].strip().lower()

    # Get all team abbreviations from box score
    teams_in_game = set()
    for player_stats in box_score.values():
        team = player_stats.get('TEAM_ABBREVIATION', '').lower()
        if team:
            teams_in_game.add(team)

    # Try to match team names
    matched_teams = 0
    for full_name, variations in TEAM_NAME_MAP.items():
        variations_lower = [v.lower() for v in variations]

        # Check if away team matches
        if any(v in away_team for v in variations_lower) or full_name.lower() in away_team:
            # Check if team abbreviation is in the game
            abbrev = variations[-1].lower()  # Last variation is usually the abbreviation
            if abbrev in teams_in_game:
                matched_teams += 1

        # Check if home team matches
        if any(v in home_team for v in variations_lower) or full_name.lower() in home_team:
            abbrev = variations[-1].lower()
            if abbrev in teams_in_game:
                matched_teams += 1

    return matched_teams >= 2


def grade_bets_for_date(date: str, db_path: str = None) -> Dict:
    """
    Grade all bets for a specific date.

    Only grades the first occurrence of each unique bet (by unique_key) to prevent
    double-counting when re-alerts are sent for improved odds/EV.

    Args:
        date: Date string 'YYYY-MM-DD'
        db_path: Optional database path

    Returns:
        Dict with grading results summary
    """
    logger.info(f"Starting grading for {date}")

    # Get ungraded bets for this date
    bets = bet_logger.get_bets_by_date(date, db_path)
    ungraded_bets = [b for b in bets if b.get('result') is None]

    if not ungraded_bets:
        logger.info(f"No ungraded bets for {date}")
        return {'date': date, 'total': 0, 'graded': 0, 'skipped': 0}

    # Deduplicate: only grade the first occurrence of each unique bet
    # This handles any duplicates that made it into the database before the fix
    seen_keys = set()
    unique_bets = []
    duplicate_ids = []

    for bet in ungraded_bets:
        key = bet.get('unique_key', f"{bet['player']}|{bet['market']}|{bet['side']}|{bet.get('line', 0)}")
        if key not in seen_keys:
            seen_keys.add(key)
            unique_bets.append(bet)
        else:
            # Mark duplicate as void so it's not counted
            duplicate_ids.append(bet['id'])
            logger.debug(f"Skipping duplicate bet {bet['id']}: {key}")

    # Mark duplicates as void
    for dup_id in duplicate_ids:
        bet_logger.update_bet_result(dup_id, 'void', 0.0, db_path)

    ungraded_bets = unique_bets
    logger.info(f"Found {len(ungraded_bets)} unique ungraded bets for {date} ({len(duplicate_ids)} duplicates marked void)")

    # Get games for the date
    games = get_games_for_date(date)
    if not games:
        logger.warning(f"No games found for {date}")
        return {'date': date, 'total': len(ungraded_bets), 'graded': 0, 'skipped': len(ungraded_bets)}

    # Cache box scores by game ID
    box_scores = {}
    first_basket_cache = {}

    results = {
        'date': date,
        'total': len(ungraded_bets),
        'graded': 0,
        'skipped': 0,
        'wins': 0,
        'losses': 0,
        'pushes': 0,
        'dnp': 0,
        'void': 0,
        'total_pl': 0.0
    }

    for bet in ungraded_bets:
        try:
            player_name = bet['player']
            bet_game = bet.get('game', '')

            # Find the game this bet belongs to by checking box scores
            matched_game_id = None
            matched_box_score = None

            for game in games:
                game_id = game['game_id']

                # Get box score (cached)
                if game_id not in box_scores:
                    box_scores[game_id] = get_box_score(game_id)

                box_score = box_scores[game_id]

                if not box_score:
                    continue

                # Check if player is in this game's box score
                player_stats = find_player_in_box_score(player_name, box_score)
                if player_stats:
                    matched_game_id = game_id
                    matched_box_score = box_score
                    break

            if not matched_game_id or not matched_box_score:
                logger.warning(f"Could not find player {player_name} in any game for {date}")
                results['skipped'] += 1
                continue

            # Find player stats
            player_stats = find_player_in_box_score(player_name, matched_box_score)

            # Get first basket info if needed
            first_basket_info = None
            if bet['market'] in ['First Basket', 'First Team Basket']:
                if matched_game_id not in first_basket_cache:
                    first_basket_cache[matched_game_id] = get_play_by_play(matched_game_id)
                first_basket_info = first_basket_cache[matched_game_id]

            # Grade the bet
            result, profit_loss = grade_bet(bet, player_stats, first_basket_info)

            # Update the bet record
            bet_logger.update_bet_result(bet['id'], result, profit_loss, db_path)

            # Update summary
            results['graded'] += 1
            results['total_pl'] += profit_loss

            if result == 'win':
                results['wins'] += 1
            elif result == 'loss':
                results['losses'] += 1
            elif result == 'push':
                results['pushes'] += 1
            elif result == 'dnp':
                results['dnp'] += 1
            elif result == 'void':
                results['void'] += 1

            logger.info(f"Graded bet {bet['id']}: {bet['player']} {bet['market']} {bet['side']} {bet.get('line', '')} -> {result} ({profit_loss:+.2f}u)")

        except Exception as e:
            logger.error(f"Error grading bet {bet['id']}: {e}")
            results['skipped'] += 1

    logger.info(f"Grading complete for {date}: {results['graded']} graded, {results['wins']}W-{results['losses']}L-{results['pushes']}P, {results['total_pl']:+.2f}u")

    return results


def grade_yesterday() -> Dict:
    """Grade all bets from yesterday."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    return grade_bets_for_date(yesterday)


def grade_all_ungraded(db_path: str = None) -> List[Dict]:
    """Grade all ungraded bets across all dates."""
    ungraded = bet_logger.get_ungraded_bets(db_path)

    if not ungraded:
        return []

    # Group by date
    dates = set(b['game_date'] for b in ungraded if b.get('game_date'))

    all_results = []
    for date in sorted(dates):
        results = grade_bets_for_date(date, db_path)
        all_results.append(results)

    return all_results
