import requests
import os
import re
import time
import secrets

from flask import Flask, redirect, render_template
from flask import request, session
from dotenv import load_dotenv
from sql_lite import db, NameLookup, BuffLookup
from patch import fetch_patch, steam_to_html


template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'steam.env'))
load_dotenv(env_path)
secret = os.getenv("SECRET_KEY")
if not secret:
    secret = secrets.token_hex(32)
    try:
        with open(env_path, 'a', encoding='utf-8') as f:
            f.write(f"\nSECRET_KEY={secret}\n")
    except Exception:
        # If writing fails, continue with the generated secret (ephemeral)
        pass
app.secret_key = secret
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'deadlock.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

region = "NAmerica"



def fetch_leaderboard(region):
    url = f'https://api.deadlock-api.com/v1/leaderboard/{region}'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print('Successfully fetched posts from API.')
            return response.json()
        else:
            print('Error: failed to fetch posts from API, response status code:', response.status_code)
            return None
    except requests.exceptions.RequestException as e:
        print('Error:', e)
        return None

def fetch_account(steamid):
    url = f'https://api.deadlock-api.com/v1/players/steam-search?search_query={steamid}'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print('Successfully fetched posts from API.')
            return response.json()
        else:
            print('Error: failed to fetch posts from API, response status code:', response.status_code)
            return None
    except requests.exceptions.RequestException as e:
        print('Error:', e)
        return None



def fetch_match_history(steamid, days=60):
    url = f'https://api.deadlock-api.com/v1/players/{steamid}/match-history'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print('Successfully fetched posts from API.')
            data = response.json()
            cutoff = time.time() - (days * 86400)
            filtered_output = [
                item for item in data
                if item.get('match_mode') == 4
                and item.get('game_mode') == 1
                and item.get('start_time', 0) >= cutoff
            ]
            return filtered_output
        else:
            print('Error: failed to fetch posts from API, response status code:', response.status_code)
            return None
    except requests.exceptions.RequestException as e:
        print('Error:', e)
        return None

def get_team_name(team_id):
    team_names = {0: 'Amber', 1: 'Sapphire'}
    return team_names.get(team_id, 'Unknown')

def format_duration(entry):
    minutes, seconds = divmod(entry['match_duration_s'], 60)
    entry['match_duration_min'] = minutes
    entry['match_duration_sec'] = seconds
    return entry

def calculate_net_worth_per_min(entry):
    total_minutes = entry['match_duration_s'] / 60
    entry['net_worth_per_min'] = round(entry['net_worth'] / total_minutes, 1) if total_minutes > 0 else 0
    return entry

def calculate_win_loss_ratio(matches):
    wins = sum(1 for m in matches if m.get('result') == 'Win')
    losses = sum(1 for m in matches if m.get('result') == 'Loss')
    total = wins + losses
    return {
        'wins': wins,
        'losses': losses,
        'win_loss_ratio': round(wins / total * 100, 2) if total > 0 else 0
    }

def label_match_result(entry):
    entry['result'] = 'Win' if entry.get('match_result') == entry.get('player_team') else 'Loss'
    return entry

def get_hero_name(hero_id):
    hero = db.session.get(NameLookup, hero_id)
    return hero.name if hero else 'Unknown'


def label_hero_name(entry):
    hero = db.session.get(NameLookup, entry.get('id'))
    entry['hero_name'] = hero.name if hero else 'Unknown'
    return entry


PREFIX_TO_NAME = {
    'firerate': 'fire_rate',
    'ammo': 'max_ammo',
    'hp': 'max_health',
    'cd': 'cooldown_reduction',
    'wp': 'weapon_damage',  
    'spirit': 'spirit_power',
    'bulletresist': 'bullet_resist',
    'speed': 'movement_speed',
    'spiritresist': 'spirit_resist',
    'range': 'ability_range',
}

def parse_buff_type(type_string):
    match = re.match(r'^([a-z]+)_permanent_pickup(?:_lv(\d+))?$', type_string)

    if not match:
        return None, 1

    prefix, level = match.groups()

    name = PREFIX_TO_NAME.get(prefix)

    if level is None:
        level = 1
    else:
        level = int(level)

    return name, level


def get_buff_info(type_string):
    name, level = parse_buff_type(type_string)
    return BuffLookup.query.filter_by(name=name, buff_lvl=level).first()

def process_power_up_buffs(player):
    result = []
    for b in player.get('power_up_buffs', []):
        raw_type = b.get('type')
        buff_info = get_buff_info(raw_type)

        result.append({
            'display_name': buff_info.name if buff_info else raw_type,
            'buff_lvl': buff_info.buff_lvl if buff_info else None,
            'buff_color': buff_info.buff_type if buff_info else None,
            'stack_count': b.get('value'),
            'per_stack_amount': buff_info.buff_ammount if buff_info else None,
            'is_permanent': b.get('is_permanent'),
        })
    return result

def calculate_total_gold_death_loss(player):
    stats = player.get('stats', [])
    values = [s.get('gold_death_loss', 0) for s in stats if s.get('gold_death_loss') is not None]
    return max(values) if values else 0

def calculate_total_buffs(player):
    buffs = process_power_up_buffs(player)
    totals = {}
    for buff in buffs:
        if buff['per_stack_amount'] is None:
            continue
        total_for_this_buff = buff['stack_count'] * buff['per_stack_amount']
        totals[buff['display_name']] = totals.get(buff['display_name'], 0) + total_for_this_buff
    return totals

def process_match_players(match_info):
    winning_team = match_info['winning_team']
    duration_s = match_info['duration_s']
    for player in match_info['players']:
        player['result'] = 'Win' if player['team'] == winning_team else 'Loss'
        player['team_name'] = get_team_name(player['team'])
        player['hero_name'] = get_hero_name(player['hero_id'])
        player['match_duration_s'] = duration_s
        player['buffs'] = process_power_up_buffs(player)
        player['gold_death_loss'] = calculate_total_gold_death_loss(player)
        calculate_net_worth_per_min(player)
    return match_info['players']

def match_result(match_id):
    url = f'https://api.deadlock-api.com/v1/matches/{match_id}/metadata'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print('Successfully fetched posts from API.')
            return response.json()
        else:
            print('Error: failed to fetch posts from API, response status code:', response.status_code)
            return None
    except requests.exceptions.RequestException as e:
        print('Error:', e)
        return None

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        raw_input = request.form.get('steamid')

        if not raw_input:
            return 'Please enter a Steam ID or profile URL.'

        numbers = re.findall(r'\d+', raw_input)

        if not numbers:
            return 'Please enter a valid numeric Steam ID.'

        steamid = numbers[0]  # take the first number sequence found

        session['steamid'] = steamid
        return redirect(('match-history'))  # send them to match history

    return render_template('form.html')

@app.route('/leaderboard', methods=['GET'])
def home():
    posts = fetch_leaderboard(region)
    if posts:
        return render_template('leaderboard.html', leader_board=posts['entries'])
    else:
        return 'Failed to fetch posts from API.'


@app.route('/steam', methods=['GET'])
def account():
    steamid = session.get('steamid')
    if not steamid:
        return 'Steam ID is required.'
    posts = fetch_account(steamid)
    if posts:
        return render_template('steam.html', accounts=posts)
    else:
        return 'Failed to fetch account from API.'

@app.route('/')
def patch():
    data = fetch_patch()
    if data is None:
        return "Error fetching patch data."

    event = data["events"][0]["announcement_body"]
    body_html = steam_to_html(event["body"])
    match = re.search(r'\d{2}-\d{2}-\d{4}', event["headline"])
    date = match.group() if match else ""
    return render_template('patch.html', body=body_html, date=date)

@app.route('/match-history', methods=['GET'])
def match_history():
    steamid = session.get('steamid')
    if not steamid:
        return 'Steam ID is required.'

    print("Loaded STEAM_ID:", steamid)

    posts = fetch_match_history(steamid)
    if not posts:
        print(steamid)
        return 'Failed to fetch account from API.'

    for entry in posts:
        format_duration(entry)
        calculate_net_worth_per_min(entry)
        label_match_result(entry)

    record = calculate_win_loss_ratio(posts)

    return render_template('test.html', match_history=posts, record=record)


@app.route('/match_history/<match_id>', methods=['GET'])
def match_detail(match_id):
    data = match_result(match_id)
    if not data:
        return 'Match not found.'

    match_info = data['match_info']
    players = process_match_players(match_info)
    minutes, seconds = divmod(match_info['duration_s'], 60)

    return render_template(
        'match_detail.html',
        match_id=match_info['match_id'],
        duration_min=minutes,
        duration_sec=seconds,
        winning_team=match_info['winning_team'],
        team0_name=get_team_name(0),
        team1_name=get_team_name(1),
        team0_players=[p for p in players if p['team'] == 0],
        team1_players=[p for p in players if p['team'] == 1]
    )

    
if __name__ == '__main__':
    app.run(debug=True)