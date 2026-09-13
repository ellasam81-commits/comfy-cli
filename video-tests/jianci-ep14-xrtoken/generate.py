"""Episode 14: one submission per shot; use GitHub's XRTOKEN secret only."""
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
OUT = Path('output/jianci-ep14-xrtoken')


def main():
    cfg = json.loads((ROOT / 'episode.json').read_text())
    assert cfg['episode'] == 14 and len(cfg['clips']) == 6
    assert sum(c['duration'] for c in cfg['clips']) == 60
    assert cfg['resolution'] == '480P' and cfg['model'] == 'wan3.0-video'
    if os.environ.get('JIANCI_EP14_EXECUTE') != '1':
        print('Dry run: 60 seconds, 480P, USD 1.764 published estimate, no requests')
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
    report = {'episode': 14, 'provider': 'XRToken', 'base_url': host, 'model': cfg['model'],
              'estimate_usd': cfg['estimate_usd'], 'max_output_seconds': 60, 'clips': []}

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
        content = [{'type': 'text', 'text': c['prompt']}]
        for ref in extra_ref or []:
            content.append({'type': 'image_url', 'image_url': {'url': ref}, 'role': 'reference_image'})
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

    def known_media(task_id, name):
        # Read only exact previous-episode tasks used as continuity references.
        res = request('/v1/videos/generations/' + task_id)
        if res.get('status') != 'succeeded':
            raise RuntimeError('Continuity source unavailable; no paid submission')
        url = res.get('video_url') or (res.get('content') or {}).get('video_url')
        if not url or urllib.parse.urlparse(url).scheme != 'https':
            raise RuntimeError('Invalid media URL')
        dest = Path('/tmp/ep14-references') / name
        dest.parent.mkdir(exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as media:
            dest.write_bytes(media.read())
        return dest

    def reference(src, seconds, name):
        dest = Path('/tmp/ep14-references') / (name + '.jpg')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(seconds), '-i', str(src),
                        '-frames:v', '1', '-vf', 'crop=854:328:0:74', str(dest)], check=True)
        return 'data:image/jpeg;base64,' + base64.b64encode(dest.read_bytes()).decode()

    save()
    mother_media = known_media('9e47037c-638a-43cd-8ae8-a32d7e189251', 'mother.mp4')
    jian_media = known_media('618bdd06-071b-41a7-ae0e-40638518e5b0', 'jian.mp4')
    mother = reference(mother_media, 1, 'mother')
    jian = reference(jian_media, 6, 'jian')
    photo = reference(mother_media, 9.6, 'photo')
    refs = {'mother': [mother], 'lin': [cfg['reference_url']], 'jian': [jian],
            'doctor_new': [jian], 'jian_photo': [jian, photo]}
    for clip in cfg['clips'][:4]:
        if not submit(clip, refs[clip['reference']]):
            raise SystemExit(2)
    if not poll(report['clips'][:4]):
        raise SystemExit(2)
    doctor = reference(OUT / '04-raw.mp4', 2, 'doctor')
    if not submit(cfg['clips'][4], [doctor]):
        raise SystemExit(2)
    if not submit(cfg['clips'][5], refs['jian_photo']):
        raise SystemExit(2)
    if not poll(report['clips'][4:]):
        raise SystemExit(2)
    print('Six Episode 14 clips downloaded; require audiovisual review', flush=True)


if __name__ == '__main__':
    main()
