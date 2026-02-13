#!/usr/bin/env python3
"""
Launcher for Pusher streaming client.
Gets stream config via Python (which handles DNS better), then launches Node.js.
"""

import json
import os
import subprocess
import sys
import requests

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"


def get_stream_config(max_retries=5):
    """Get stream configuration with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(
                f"{BASE_URL}/stream/events",
                headers={'x-api-key': API_KEY},
                params={'feed': 'events:upcoming', 'leagueID': 'NBA'},
                timeout=30
            )
            if r.status_code == 503:
                print(f"API returned 503, retry {attempt}/{max_retries}...")
                import time
                time.sleep(2 * attempt)
                continue
            if r.status_code == 200:
                return r.json()
            print(f"HTTP {r.status_code}")
        except Exception as e:
            print(f"Request failed: {e}, retry {attempt}/{max_retries}...")
            import time
            time.sleep(2 * attempt)
    return None


def main():
    print("=" * 60)
    print("SportsGameOdds Stream Launcher")
    print("=" * 60)

    print("\n[INIT] Fetching stream configuration via Python...")
    config = get_stream_config()

    if not config:
        print("[ERROR] Failed to get stream config")
        sys.exit(1)

    print(f"[INIT] Pusher Key: {config['pusherKey']}")
    print(f"[INIT] Channel: {config['channel']}")
    print(f"[INIT] Events: {len(config.get('data', []))}")

    # Save config to file for Node.js
    config_file = '/tmp/sgo_stream_config.json'
    with open(config_file, 'w') as f:
        json.dump(config, f)

    print(f"\n[LAUNCH] Starting Node.js Pusher client...")

    # Launch Node.js with config file path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    node_script = os.path.join(script_dir, 'pusher_stream_v2.js')

    env = os.environ.copy()
    env['SGO_CONFIG_FILE'] = config_file

    try:
        subprocess.run(['node', node_script], env=env, cwd=script_dir)
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")


if __name__ == "__main__":
    main()
