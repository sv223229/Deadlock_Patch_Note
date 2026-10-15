import requests
import os
import re
import time

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

IMG_PATTERN = re.compile(
    r'\[img(?:\s+src\s*=\s*["\']([^"\']*)["\'])?\s*\](.*?)\[/img\]',
    re.DOTALL | re.IGNORECASE,
)

def extract_images(text):
    urls = []
    for m in IMG_PATTERN.finditer(text):
        url = (m.group(1) or m.group(2)).strip()
        url = url.replace('{STEAM_CLAN_LOC_IMAGE}', CLAN_IMAGE_BASE).replace('{STEAM_CLAN_IMAGE}', CLAN_IMAGE_BASE)
        if url:
            urls.append(url)
    return urls

def clean_bbcode(text):
    text = IMG_PATTERN.sub('', text)

    def _url_repl(m):
        href, label = m.group(1), m.group(2).strip()
        return href if (not label or label == href) else f'{label} ({href})'
    text = re.sub(r'\[url=([^\]]+)\](.*?)\[/url\]', _url_repl, text, flags=re.DOTALL)
    text = re.sub(r'\[url\](.*?)\[/url\]', r'\1', text, flags=re.DOTALL)

    for tag in ['b', 'i', 'u', 'strike']:
        text = text.replace(f'[{tag}]', '').replace(f'[/{tag}]', '')

    text = text.replace('\\[', '[').replace('\\]', ']')
    return text.strip()

def parse_patch_notes(text):
    text = text.replace('\r\n', '\n')
    if '[p]' in text:
        # each [p]...[/p] becomes its own line; an empty [p][/p] becomes a blank line
        text = re.sub(r'\[p\](.*?)\[/p\]', lambda m: m.group(1) + '\n', text, flags=re.DOTALL)

    sections = []
    group = []          # consecutive non-blank lines = one card

    def current_section():
        if not sections:
            sections.append({'header': None, 'bullets': [], 'images': []})
        return sections[-1]

    def flush():
        if group:
            current_section()['bullets'].append('\n'.join(group))
            group.clear()

    for raw in text.split('\n'):
        raw = raw.strip()
        if not raw:
            flush()                     # blank line = gap between groups
            continue

        images = extract_images(raw)    # must run BEFORE clean_bbcode strips the tags
        is_header = raw.startswith('[b]') and raw.endswith('[/b]')
        clean = clean_bbcode(raw)

        if is_header and clean:
            flush()
            if clean.startswith('- '):
                clean = clean[2:]
            sections.append({'header': clean, 'bullets': [], 'images': images})
            continue

        if images:
            current_section()['images'].extend(images)
        if clean:
            group.append(clean)

    flush()
    return sections

data = fetch_patch()

body = data["events"][0]["announcement_body"]["body"]
sections = parse_patch_notes(body)
# print(sections)

headline = data["events"][0]["announcement_body"]["headline"]

match = re.search(r'\d{2}-\d{2}-\d{4}', headline)

if match:
    date = match.group()
    print(date)
else:
    print("No date found in headline:", headline)