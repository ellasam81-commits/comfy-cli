"""Bounded Jianci production: retrieve references or submit explicitly listed clips."""
import base64
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
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
        print(clip['id'], 'submitted', flush=True)
    except urllib.error.HTTPError as exc:
        message = exc.read(1500).decode('utf-8', 'replace')
        message = message.replace(os.environ['XRTOKEN'].strip(), '[REDACTED]')
        row.update(state='SUBMISSION_HTTP_ERROR', http_status=exc.code, error=message)
        save(row)
        print(clip['id'], 'HTTP rejection', exc.code, flush=True)
        return row
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
                print(clip['id'], row['state'], flush=True)
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


class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Authenticated redirect refused')


def segmind_api(path, body=None, upload=False):
    key = os.environ['SEGMIND_API_KEY'].strip()
    assert key, 'Missing SEGMIND_API_KEY'
    assert path.startswith(('/v1/', '/v2/')) or (upload and path == '/upload-asset')
    host = 'https://workflows-api.segmind.com' if upload else 'https://api.segmind.com'
    req = urllib.request.Request(host + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'x-api-key': key, 'Content-Type': 'application/json'})
    with urllib.request.build_opener(NoAuthRedirect).open(req, timeout=90) as res:
        return json.load(res)


def output_urls(value):
    if isinstance(value, str) and value.startswith('https://'):
        return [value]
    if isinstance(value, list):
        return [u for v in value for u in output_urls(v)]
    if isinstance(value, dict):
        return [u for k in ('output', 'video', 'video_url', 'url', 'output_url', 'data')
                if k in value for u in output_urls(value[k])]
    return []


def execute_segmind(clip, refs):
    row = {'id': clip['id'], 'provider': 'segmind', 'state': 'SUBMITTING',
           'max_submissions': 1, 'estimated_usd': clip['duration'] * 0.05,
           'dialogue': clip['lines']}
    save(row)
    try:
        q = segmind_api('/v2/wan3.0-video', {
            'prompt': clip['prompt'], 'reference_images': [refs[n] for n in clip['refs']],
            'duration': clip['duration'], 'resolution': '480P', 'aspect_ratio': '16:9',
            'audio': True, 'watermark': False, 'prompt_extend': False,
            'enable_thinking': False, 'seed': clip['seed']})
        tid = q['request_id']
        assert isinstance(tid, str) and re.fullmatch(r'[A-Za-z0-9_-]+', tid)
        row.update(task_id=tid, state='QUEUED')
        save(row)
        print(clip['id'], 'Segmind submitted', flush=True)
    except urllib.error.HTTPError as exc:
        row.update(state='SUBMISSION_HTTP_ERROR', http_status=exc.code)
        save(row)
        return row
    except Exception as exc:
        row.update(state='SUBMISSION_UNKNOWN_OR_FAILED', error=type(exc).__name__)
        save(row)
        return row
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        try:
            path = '/v2/requests/' + tid
            q = segmind_api(path + '/status')
            row['state'] = q.get('status')
            save(row)
            if row['state'] == 'COMPLETED':
                q = segmind_api(path)
                urls = output_urls(q.get('output', q))
                assert urls, 'No output URL'
                dst = OUT / (clip['id'] + '-raw.mp4')
                get_file(urls[0], dst)
                meta = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                    '-show_streams', '-show_format', '-of', 'json', str(dst)]))
                row['has_audio'] = any(s['codec_type'] == 'audio' for s in meta['streams'])
                row['duration'] = meta['format']['duration']
                row['state'] = 'succeeded' if row['has_audio'] else 'MISSING_AUDIO'
                save(row)
                return row
            if row['state'] == 'FAILED':
                return row
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                row.update(state='FAILED', http_status=422)
                save(row)
                return row
            row['poll_http_error'] = exc.code
            save(row)
        except Exception as exc:
            row['poll_error'] = type(exc).__name__
            save(row)
        time.sleep(12)
    row['state'] = 'TIMEOUT_RETAIN_TASK_ID'
    save(row)
    return row


def segmind_main(req, selected):
    # Fixed model/price and explicit prior-spend ledger; never autosubmit retries.
    from decimal import Decimal
    assert req['provider'] == 'segmind'
    assert Decimal(str(req['budget_usd'])) <= Decimal('7')
    spent = Decimal(str(req['prior_committed_usd']))
    assert spent >= 0
    durations = req['durations']
    for c in selected:
        d = durations[c['id']]
        assert isinstance(d, int) and 2 <= d <= 10
        c['duration'] = d
        if c['id'] in req.get('prompt_overrides', {}):
            c['prompt'] = req['prompt_overrides'][c['id']]
            assert isinstance(c['prompt'], str) and len(c['prompt']) <= 5000
        c['prompt'] = c['prompt'].replace('10-second', str(d) + '-second')
        c['prompt'] = c['prompt'].replace('by 8.8 sec', 'by ' + str(d - 0.5) + ' sec')
    estimate = sum(Decimal(c['duration']) * Decimal('0.05') for c in selected)
    assert spent + estimate <= Decimal(str(req['budget_usd']))
    segmind_api('/v1/get-user-credits')  # Read-only authentication check; no secret output.
    names = sorted({n for c in selected for n in c['refs']})
    data_urls = [reference(n) for n in names]
    uploaded = segmind_api('/upload-asset', {'data_urls': data_urls}, upload=True)
    urls = uploaded['file_urls']
    assert len(urls) == len(names) and all(u.startswith('https://') for u in urls)
    refs = dict(zip(names, urls))
    (OUT / 'budget.json').write_text(json.dumps({'budget_usd': req['budget_usd'],
        'prior_committed_usd': float(spent), 'batch_estimate_usd': float(estimate),
        'maximum_after_batch_usd': float(spent + estimate),
        'actual_billing': 'Provider request history is authoritative'}))
    results = []
    workers = req.get('workers', 1)
    assert isinstance(workers, int) and 1 <= workers <= 3
    for start in range(0, len(selected), workers):
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            batch = list(pool.map(lambda c: execute_segmind(c, refs), selected[start:start + workers]))
        results.extend(batch)
        (OUT / 'batch-report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
        # No new wave after failed/ambiguous jobs; accepted jobs retain receipts.
        if any(row['state'] != 'succeeded' for row in batch):
            raise SystemExit(2)


def main():
    req = json.loads((ROOT / 'run.request.json').read_text())
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'No duplicate paid reruns'
    OUT.mkdir(parents=True, exist_ok=True)
    if req['mode'] == 'segmind_diagnostics':
        details = {'paid_submissions': 0, 'tasks': []}
        credits = segmind_api('/v1/get-user-credits')
        def numeric(v):
            if isinstance(v, dict):
                return {k: numeric(x) for k, x in v.items() if isinstance(x, (dict, int, float)) or (isinstance(x, str) and re.fullmatch(r'[0-9.]+', x))}
            return v
        details['credits'] = numeric(credits)
        for tid in req['task_ids']:
            assert re.fullmatch(r'[A-Za-z0-9_-]+', tid)
            try:
                q = segmind_api('/v2/requests/' + tid + '/status')
            except urllib.error.HTTPError as exc:
                body = exc.read(6000).decode('utf-8', 'replace')
                body = body.replace(os.environ['SEGMIND_API_KEY'].strip(), '[REDACTED]')
                q = {'http_status': exc.code, 'detail': body}
            details['tasks'].append({'task_id': tid, 'response': q})
        (OUT / 'segmind-diagnostics.json').write_text(json.dumps(details, ensure_ascii=False, indent=2))
        print('Read-only Segmind diagnostics saved; no generation calls.')
        return
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
    if req.get('provider') == 'segmind':
        return segmind_main(req, selected)
    refs = {name: reference(name) for name in sorted({n for c in selected for n in c['refs']})}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda c: execute(c, refs), selected))
    (OUT / 'batch-report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r['state'] != 'succeeded' for r in results):
        raise SystemExit(2)

if __name__ == '__main__':
    main()
