"""Episode 13: one submission per shot; use GitHub's XRTOKEN secret only."""
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT = Path('output/jianci-ep13-xrtoken')


def main():
    cfg = json.loads((ROOT / 'episode.json').read_text())
    assert cfg['episode'] == 13 and len(cfg['clips']) == 9
    assert sum(c['duration'] for c in cfg['clips']) == 90
    assert cfg['resolution'] == '480P' and cfg['model'] == 'wan3.0-video'
    if os.environ.get('JIANCI_EP13_EXECUTE') != '1':
        print('Dry run: 90 seconds, 480P, USD 2.646 published estimate, no requests')
        return
    if os.environ.get('GITHUB_RUN_ATTEMPT', '1') != '1':
        raise RuntimeError('No duplicate paid rerun; recover saved task IDs instead')
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'report.json').exists():
        raise RuntimeError('Existing report: refuse duplicate paid submission')
    key = os.environ['XRTOKEN'].strip()
    if not key:
        raise RuntimeError('XRTOKEN missing')
    host = 'https://api.xrtoken.ai'
    report = {'episode': 13, 'provider': 'XRToken', 'base_url': host, 'model': cfg['model'],
              'estimate_usd': cfg['estimate_usd'], 'max_output_seconds': 90, 'clips': []}

    def save():
        tmp = OUT / 'report.tmp'
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        tmp.replace(OUT / 'report.json')

    def request(path, body=None):
        headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(host + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=90) as res:
            return json.load(res)

    def errinfo(exc):
        result = {'error_type': type(exc).__name__}
        if isinstance(exc, urllib.error.HTTPError):
            result['http_status'] = exc.code
            try:
                msg = exc.read(3000).decode(errors='replace').replace(key, '[REDACTED]')
                result['provider_error'] = msg
            except Exception:
                pass
        return result

    def submit(c, extra_ref=None):
        row = {'id': c['id'], 'state': 'SUBMITTING', 'duration': c['duration']}
        report['clips'].append(row)
        save()
        content = [{'type': 'text', 'text': c['prompt']},
                   {'type': 'image_url', 'image_url': {'url': cfg['reference_url']}, 'role': 'reference_image'}]
        if extra_ref:
            content.append({'type': 'image_url', 'image_url': {'url': extra_ref}, 'role': 'reference_image'})
        body = {'model': cfg['model'], 'content': content, 'duration': c['duration'],
                'resolution': '480P', 'ratio': '16:9', 'generate_audio': True,
                'watermark': False, 'prompt_extend': False, 'seed': 906181}
        try:
            res = request('/v1/videos/generations', body)
            task_id = res.get('id') or res.get('data', {}).get('id')
            if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+', task_id):
                raise RuntimeError('Missing task ID; do not resubmit')
            row.update(task_id=task_id, state=res.get('status', 'queued'))
            print('Accepted', c['id'], task_id, flush=True)
        except Exception as exc:
            row.update(state='SUBMISSION_UNKNOWN_OR_FAILED', **errinfo(exc))
            print('Submission stopped', c['id'], row.get('http_status', row['error_type']), flush=True)
            save()
            return False
        save()
        return True

    def poll(rows):
        pending = list(rows)
        deadline = time.monotonic() + 2100
        while pending and time.monotonic() < deadline:
            for row in list(pending):
                try:
                    res = request('/v1/videos/generations/' + urllib.parse.quote(row['task_id'], safe=''))
                    state = res.get('status', 'unknown')
                    row['state'] = state
                    if state == 'succeeded':
                        content = res.get('content') or {}
                        url = res.get('video_url') or (content.get('video_url') if isinstance(content, dict) else None)
                        if not url or urllib.parse.urlparse(url).scheme != 'https':
                            raise RuntimeError('Missing HTTPS video URL')
                        row['video_url'] = url
                        dest = OUT / (row['id'] + '-raw.mp4')
                        # Download media without forwarding API Authorization.
                        with urllib.request.urlopen(url, timeout=120) as media:
                            dest.write_bytes(media.read())
                        row['file'] = dest.name
                        pending.remove(row)
                        print('Downloaded', row['id'], flush=True)
                    elif state in {'failed', 'cancelled', 'expired'}:
                        row['provider_error'] = str(res.get('error', ''))[:2000].replace(key, '[REDACTED]')
                        pending.remove(row)
                        print('Failed', row['id'], flush=True)
                except Exception as exc:
                    row['last_poll_error'] = errinfo(exc)
                save()
            if pending:
                time.sleep(12)
        for row in pending:
            row['state'] = 'TIMEOUT_RETAIN_TASK_ID'
        save()
        return all('file' in row for row in rows)

    def frame_ref(clip_id):
        src = OUT / (clip_id + '-raw.mp4')
        dest = OUT / (clip_id + '-continuity.jpg')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', '3', '-i', str(src),
                        '-frames:v', '1', str(dest)], check=True)
        return 'data:image/jpeg;base64,' + base64.b64encode(dest.read_bytes()).decode()

    save()
    # This read-only request was verified separately before generation.
    request('/v1/videos/generations?limit=1')
    submissions_ok = True
    for clip in cfg['clips'][:7]:
        if not submit(clip):
            submissions_ok = False
            break
    accepted = [r for r in report['clips'] if 'task_id' in r]
    finished = poll(accepted)
    if not submissions_ok or not finished or len(accepted) != 7:
        raise SystemExit(2)
    # Carry the new mother's appearance forward using already purchased frames.
    if not submit(cfg['clips'][7], frame_ref('07')) or not poll([report['clips'][-1]]):
        raise SystemExit(2)
    if not submit(cfg['clips'][8], frame_ref('08')) or not poll([report['clips'][-1]]):
        raise SystemExit(2)
    print('All nine clips downloaded; subtitle and sound editing required', flush=True)


if __name__ == '__main__':
    main()
