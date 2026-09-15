"""Bounded Jianci production: retrieve references or submit explicitly listed clips."""
import base64
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).parent
OUT = Path('output/jianci-31-36')
HOST = 'https://api.xrtoken.ai'
REFS = {
    'jian': ('266e6ebd-0a4d-408c-ae66-6b82077aa055', 2, '400:320:230:0'),
    'zhou': ('22f44ed1-b301-4b7a-9330-afa87e545dd4', 2, '400:320:150:0'),
    'lin': ('75c2593e-12b3-4c09-836f-da13c4dd8f0d', 1, '300:320:130:0'),
    'han': ('10c316b2-29cd-4145-9fc7-bed0a6bf561c', 2, '320:300:310:0'),
    'xu': ('a8f8000e-6ef7-4714-aa1f-fb1a51f6c90c', 1, '360:300:250:0'),
}

def api(path, body=None):
    key = os.environ['XRTOKEN'].strip()
    assert key
    req = urllib.request.Request(HOST + path,
        data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as res:
        return json.load(res)

def get_file(url, path):
    assert urllib.parse.urlparse(url).scheme == 'https'
    with urllib.request.urlopen(url, timeout=180) as res:
        path.write_bytes(res.read())

def reference(name):
    tid, sec, crop = REFS[name]
    q = api('/v1/videos/generations/' + tid)
    assert q.get('status') == 'succeeded', name + ' reference unavailable'
    src = OUT / ('ref-' + name + '.mp4')
    get_file(q.get('video_url') or q.get('content', {}).get('video_url'), src)
    img = OUT / ('ref-' + name + '.jpg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(sec), '-i', str(src),
        '-vf', 'crop=' + crop, '-frames:v', '1', str(img)], check=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(img.read_bytes()).decode()

def save(row):
    (OUT / (row['id'] + '-report.json')).write_text(json.dumps(row, ensure_ascii=False, indent=2))

def execute(clip, refs):
    row = {'id': clip['id'], 'state': 'SUBMITTING', 'max_submissions': 1,
           'dialogue': clip['lines']}
    save(row)
    try:
        content = [{'type': 'text', 'text': clip['prompt']}]
        for name in clip['refs']:
            content.append({'type': 'image_url', 'image_url': {'url': refs[name]}, 'role': 'reference_image'})
        # Never automatically repeat a submission: a timeout may already be billed.
        q = api('/v1/videos/generations', {'model': 'wan3.0-video', 'content': content,
            'duration': clip['duration'], 'resolution': '480P', 'ratio': '16:9',
            'generate_audio': True, 'watermark': False, 'prompt_extend': False,
            'seed': clip['seed']})
        tid = q.get('id') or q.get('data', {}).get('id')
        assert isinstance(tid, str) and re.fullmatch(r'[A-Za-z0-9_.:-]+', tid)
        row.update(task_id=tid, state=q.get('status', 'queued'))
        save(row)
    except Exception as exc:
        row.update(state='SUBMISSION_UNKNOWN_OR_FAILED', error=type(exc).__name__)
        save(row)
        return row
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        try:
            q = api('/v1/videos/generations/' + urllib.parse.quote(tid, safe=''))
            row['state'] = q.get('status')
            save(row)
            if row['state'] == 'succeeded':
                dst = OUT / (clip['id'] + '-raw.mp4')
                get_file(q.get('video_url') or q.get('content', {}).get('video_url'), dst)
                meta = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                    '-show_streams', '-show_format', '-of', 'json', str(dst)]))
                row['has_audio'] = any(s['codec_type'] == 'audio' for s in meta['streams'])
                row['duration'] = meta['format']['duration']
                row['state'] = 'succeeded' if row['has_audio'] else 'MISSING_AUDIO'
                save(row)
                return row
            if row['state'] in ('failed', 'cancelled', 'expired'):
                return row
        except Exception as exc:
            row['poll_error'] = type(exc).__name__
            save(row)
        time.sleep(12)
    row['state'] = 'TIMEOUT_RETAIN_TASK_ID'
    save(row)
    return row

def main():
    req = json.loads((ROOT / 'run.request.json').read_text())
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'No duplicate paid reruns'
    OUT.mkdir(parents=True, exist_ok=True)
    if req['mode'] == 'references':
        for name in REFS:
            reference(name)
        (OUT / 'reference-check.json').write_text(json.dumps({'state': 'ready', 'paid_submissions': 0}))
        return
    assert req['mode'] == 'generate' and os.environ.get('JIANCI_EXECUTE') == '1'
    cfg = json.loads((ROOT / 'clips.json').read_text())
    REFS.update(cfg.get('additional_refs', {}))
    selected = [c for c in cfg['clips'] if c['id'] in req['clip_ids']]
    assert len(selected) == len(set(req['clip_ids'])) <= 36
    assert sum(c['duration'] for c in selected) <= req['max_seconds']
    refs = {name: reference(name) for name in sorted({n for c in selected for n in c['refs']})}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda c: execute(c, refs), selected))
    (OUT / 'batch-report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r['state'] != 'succeeded' for r in results):
        raise SystemExit(2)

if __name__ == '__main__':
    main()
