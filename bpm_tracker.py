import sys
import os
import re
import csv
import time
from urllib.parse import quote_plus
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests

def get_playlist_id(url_or_id):
    match = re.search(r'playlist[/:]([a-zA-Z0-9]+)', url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()

def fetch_all_tracks(sp, playlist_id):
    tracks = []
    results = sp.playlist_tracks(playlist_id)
    while True:
        for item in results['items']:
            track = item.get('track')
            if track and track.get('id'):
                tracks.append(track)
        if results['next']:
            results = sp.next(results)
        else:
            break
    return tracks

def lookup_bpm_getsongbpm(api_key, title, artist):
    """Look up BPM from GetSongBPM API."""
    try:
        # Search for the song
        search_url = f"https://api.getsongbpm.com/search/?api_key={api_key}&type=song&lookup={quote_plus(title)}"
        resp = requests.get(search_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get('search', [])
        if not results:
            return None

        # Match by artist name
        artist_lower = artist.lower()
        song_id = None
        for r in results:
            r_artist = r.get('artist', {}).get('name', '').lower()
            if r_artist and (r_artist in artist_lower or artist_lower in r_artist):
                song_id = r.get('id')
                break

        # Fall back to first result
        if not song_id and results:
            song_id = results[0].get('id')

        if not song_id:
            return None

        # Get song details with BPM
        song_url = f"https://api.getsongbpm.com/song/?api_key={api_key}&id={song_id}"
        resp2 = requests.get(song_url, timeout=10)
        resp2.raise_for_status()
        song_data = resp2.json()

        tempo = song_data.get('song', {}).get('tempo')
        if tempo:
            return int(tempo)
        return None
    except Exception:
        return None

def lookup_bpm_deezer(title, artist, isrc=None):
    """Fallback: look up BPM from Deezer's free API."""
    try:
        # Try ISRC first for exact match
        if isrc:
            resp = requests.get(f'https://api.deezer.com/track/isrc:{isrc}', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                bpm = data.get('bpm')
                if bpm and bpm > 0:
                    return round(bpm)

        # Fall back to text search
        query = f"{artist} {title}"
        resp = requests.get('https://api.deezer.com/search',
            params={'q': query, 'limit': 5}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for r in data.get('data', []):
            r_artist = r.get('artist', {}).get('name', '').lower()
            if artist.lower() in r_artist or r_artist in artist.lower():
                detail = requests.get(f'https://api.deezer.com/track/{r["id"]}', timeout=10).json()
                bpm = detail.get('bpm')
                if bpm and bpm > 0:
                    return round(bpm)

        # Try first result
        results = data.get('data', [])
        if results:
            detail = requests.get(f'https://api.deezer.com/track/{results[0]["id"]}', timeout=10).json()
            bpm = detail.get('bpm')
            if bpm and bpm > 0:
                return round(bpm)

        return None
    except Exception:
        return None

def parse_selection(selection_str, total):
    selected = set()
    if selection_str.strip().lower() == 'all':
        return set(range(1, total + 1))
    for part in selection_str.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = part.split('-', 1)
                for i in range(int(start), int(end) + 1):
                    if 1 <= i <= total:
                        selected.add(i)
            except ValueError:
                pass
        else:
            try:
                i = int(part)
                if 1 <= i <= total:
                    selected.add(i)
            except ValueError:
                pass
    return selected

def main():
    client_id = os.environ.get('SPOTIPY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIPY_CLIENT_SECRET')
    bpm_api_key = os.environ.get('GETSONGBPM_API_KEY', '')

    if not client_id or not client_secret:
        print("Set Spotify credentials:")
        print('  $env:SPOTIPY_CLIENT_ID="your_id"')
        print('  $env:SPOTIPY_CLIENT_SECRET="your_secret"')
        sys.exit(1)

    if not bpm_api_key:
        print("WARNING: No GETSONGBPM_API_KEY set. Using Deezer only (lower coverage).")
        print('  Get a free key at https://getsongbpm.com/api')
        print('  $env:GETSONGBPM_API_KEY="your_key"')
        print()

    if len(sys.argv) < 2:
        print("Usage: python bpm_tracker.py <playlist_url_or_id>")
        sys.exit(1)

    playlist_input = sys.argv[1]
    playlist_id = get_playlist_id(playlist_input)

    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=client_id, client_secret=client_secret
    ))

    # Get playlist name
    playlist_info = sp.playlist(playlist_id, fields='name')
    playlist_name = playlist_info['name']
    print(f"\nPlaylist: {playlist_name}\n")

    # Fetch tracks
    print("Fetching tracks...")
    tracks = fetch_all_tracks(sp, playlist_id)
    print(f"Found {len(tracks)} tracks.")

    # Build track list
    track_list = []
    for t in tracks:
        artists = ', '.join(a['name'] for a in t['artists'])
        first_artist = t['artists'][0]['name'] if t['artists'] else ''
        isrc = t.get('external_ids', {}).get('isrc')
        track_list.append({
            'name': t['name'],
            'artists': artists,
            'first_artist': first_artist,
            'uri': t['uri'],
            'isrc': isrc,
            'bpm': None,
            'source': None
        })

    # Look up BPMs
    print(f"Looking up BPM for {len(track_list)} tracks...\n")
    found = 0
    for i, t in enumerate(track_list, 1):
        label = t['name'][:40]
        print(f"  [{i}/{len(track_list)}] {label}...", end=" ", flush=True)

        bpm = None
        source = None

        # Try GetSongBPM first
        if bpm_api_key:
            bpm = lookup_bpm_getsongbpm(bpm_api_key, t['name'], t['first_artist'])
            if bpm:
                source = 'getsongbpm'

        # Fall back to Deezer
        if not bpm:
            bpm = lookup_bpm_deezer(t['name'], t['first_artist'], t['isrc'])
            if bpm:
                source = 'deezer'

        t['bpm'] = bpm
        t['source'] = source
        if bpm:
            found += 1
            print(f"{bpm} BPM ({source})")
        else:
            print("not found")

        time.sleep(0.25)

    print(f"\nFound BPM for {found}/{len(track_list)} tracks.\n")

    # Print table
    print(f"{'#':<5} {'BPM':<6} {'Title':<45} {'Artist(s)'}")
    print("-" * 105)
    for idx, t in enumerate(track_list, 1):
        bpm_str = str(t['bpm']) if t['bpm'] else '?'
        title = t['name'][:43]
        artists = t['artists'][:40]
        print(f"{idx:<5} {bpm_str:<6} {title:<45} {artists}")

    # Interactive selection
    print(f"\nSelect songs to rip (comma-separated numbers, ranges with dashes).")
    print(f"Examples: 1,3,5-10  |  all  |  Press Enter to cancel")
    selection = input("\n> ").strip()

    if not selection:
        print("Cancelled.")
        return

    selected = parse_selection(selection, len(track_list))
    if not selected:
        print("No valid songs selected.")
        return

    chosen = [track_list[i - 1] for i in sorted(selected)]
    print(f"\nSelected {len(chosen)} songs:")
    for t in chosen:
        bpm_str = f" ({t['bpm']} BPM)" if t['bpm'] else ""
        print(f"  - {t['name']} -- {t['artists']}{bpm_str}")

    # Export files
    safe_name = re.sub(r'[^\w\s-]', '', playlist_name).strip().replace(' ', '_')

    # CSV with selected tracks + BPM
    csv_path = f"{safe_name}_selected.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Title', 'Artist(s)', 'BPM', 'Spotify URI'])
        for t in chosen:
            writer.writerow([t['name'], t['artists'], t['bpm'], t['uri']])
    print(f"\nSaved selection to: {csv_path}")

    # Soggfy URI list
    uri_path = f"{safe_name}_uris.txt"
    with open(uri_path, 'w', encoding='utf-8') as f:
        for t in chosen:
            f.write(t['uri'] + '\n')
    print(f"Saved Spotify URIs for Soggfy to: {uri_path}")

if __name__ == '__main__':
    main()
