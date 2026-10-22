import requests
import re
import html
import bbcode

def fetch_patch():
    url = f'https://store.steampowered.com/events/ajaxgetadjacentpartnerevents/?appid=1422450'
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

CLAN_IMAGE_BASE = 'https://clan.fastly.steamstatic.com/images'

def _safe_url(url):
    url = (url or '').strip().strip('"\'')
    return html.escape(url, quote=True) if re.match(r'https?://', url) else ''

def _render_img(tag_name, value, options, parent, context):
    # handles both [img]URL[/img] and [img src="URL"][/img]
    return f'<img src="{_safe_url(options.get("src") or value)}" alt="" style="max-width:100%">'

def _render_url(tag_name, value, options, parent, context):
    href = _safe_url(options.get('url') or value)
    return f'<a href="{href}" target="_blank" rel="noopener">{value}</a>'

parser = bbcode.Parser(newline='\n', escape_html=True, replace_links=False)
parser.add_simple_formatter('p', '<p>%(value)s</p>\n')
parser.add_simple_formatter('h1', '<h1>%(value)s</h1>')
parser.add_simple_formatter('h2', '<h2>%(value)s</h2>')
parser.add_simple_formatter('h3', '<h3>%(value)s</h3>')
parser.add_simple_formatter('strike', '<s>%(value)s</s>')
parser.add_simple_formatter('list', '<ul>%(value)s</ul>')
parser.add_simple_formatter('*', '<li>%(value)s</li>', newline_closes=True)
parser.add_formatter('img', _render_img, replace_links=False)
parser.add_formatter('url', _render_url, replace_links=False)

def steam_to_html(text):
    text = text.replace('{STEAM_CLAN_LOC_IMAGE}', CLAN_IMAGE_BASE)
    text = text.replace('{STEAM_CLAN_IMAGE}', CLAN_IMAGE_BASE)
    # protect Steam's escaped brackets from the tag parser, restore afterwards
    text = text.replace('\\[', '\x01').replace('\\]', '\x02')
    out = parser.format(text)
    return out.replace('\x01', '[').replace('\x02', ']')



data = fetch_patch()

body = data["events"][0]["announcement_body"]["body"]

print(steam_to_html(body))

headline = data["events"][0]["announcement_body"]["headline"]

match = re.search(r'\d{2}-\d{2}-\d{4}', headline)

if match:
    date = match.group()
    print(date)
else:
    print("No date found in headline:", headline)