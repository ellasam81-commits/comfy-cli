"""Read-only XRToken status check for this exact MV's prompts."""
import json
import os
from pathlib import Path
import urllib.request

key = os.environ['XRTOKEN'].strip()
def get(path):
    req = urllib.request.Request('https://api.xrtoken.ai' + path, headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)

data = get('/v1/videos/generations?limit=20')
items = data.get('data', data.get('items', data.get('tasks', [])))
if isinstance(items, dict):
    items = items.get('items', items.get('data', items.get('tasks', [])))
rows = []
for item in items if isinstance(items, list) else []:
    task = item.get('id')
    if not task:
        continue
    if item.get('model') not in (None, 'wan3.0-video'):
        continue
    detail = get('/v1/videos/generations/' + task)
    if 'Create a fully animated cinematic 2D anime fantasy romance music-video scene' in json.dumps(detail):
        rows.append({'id': task, 'status': detail.get('status'), 'video_url': detail.get('video_url') or (detail.get('content') or {}).get('video_url'), 'created_at': detail.get('created_at'), 'seed': detail.get('seed')})
out = Path('output/tanhuo-status');out.mkdir(parents=True, exist_ok=True)
(out / 'status.json').write_text(json.dumps({'list_keys': list(data), 'listed': len(items), 'matched': rows}, indent=2))
print(json.dumps({'listed':len(items),'matched':[{k:v for k,v in r.items() if k != 'video_url'} for r in rows]}))
