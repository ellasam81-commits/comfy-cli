"""Six authorized WAN clips; never retry a paid creation request."""
import argparse
import base64
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
OUT = Path('output/drop-promo')
HOST = 'https://api.xrtoken.ai'
SOURCE = 'https://cdn.creativeclaw.co/u/b3866ea4/audio/509f594c-d6e9-4987-93ba-20bd44721aed.mp3'
LOCK = threading.RLock()
CFG = json.loads((ROOT / 'plan.json').read_text())
COMMON = CFG['common']
SHOTS = [(x['id'],x['ref'],x['action'],x['duration']) for x in CFG['shots']]

def run(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p.stdout

def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    assert len(SHOTS) == 6
    assert all((ROOT / 'refs' / (ref + '.jpg')).is_file() for _, ref, _, _ in SHOTS)
    if not args.execute:
        print('VALID: six clips, 30 paid seconds maximum, 30s final; Drop source 90-120s; no paid retries')
        return
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'Do not blindly rerun paid jobs'
    key = os.environ['XRTOKEN'].strip()
    assert key
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / 'report.json'
    assert not report_path.exists(), 'Existing report: recover tasks rather than resubmit'
    report = {'model': 'wan3.0-video', 'resolution': '480P', 'max_paid_seconds': 30, 'target_duration': 30, 'clips': []}

    def save():
        with LOCK:
            tmp = OUT / 'report.tmp'
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            tmp.replace(report_path)

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(HOST + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)

    def download(url, path):
        assert url.startswith('https://')
        with urllib.request.urlopen(url, timeout=240) as r:
            path.write_bytes(r.read())

    save()
    # Ensure original song is accessible before any paid creation.
    download(SOURCE, OUT / 'source.mp4')
    source_info = probe(OUT / 'source.mp4')
    assert any(s['codec_type'] == 'audio' for s in source_info['streams'])
    request('/v1/videos/generations?limit=1')

    def generate(shot):
        sid, ref, action, duration = shot
        row = {'id': sid, 'state': 'SUBMITTING', 'requested_duration': duration}
        with LOCK:
            report['clips'].append(row)
            save()
        content = [{'type': 'text', 'text': COMMON + action}]
        for r in [ref, '02']:
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'refs' / (r + '.jpg')).read_bytes()).decode()}, 'role': 'reference_image'})
        payload = {'model': 'wan3.0-video', 'duration': duration, 'resolution': '480P', 'ratio': '16:9', 'generate_audio': False, 'watermark': False, 'prompt_extend': False, 'seed': 929700 + int(sid), 'content': content}
        try:
            data = request('/v1/videos/generations', payload)  # Exactly ONE paid POST per shot.
            task = data.get('id') or data.get('data', {}).get('id')
            assert isinstance(task, str) and re.fullmatch(r'[A-Za-z0-9_.:-]+', task)
            with LOCK:
                row.update(task_id=task, state=data.get('status', 'queued'))
                save()
            print('Accepted', sid, task, flush=True)
            deadline = time.monotonic() + 3000
            while time.monotonic() < deadline:
                try:
                    data = request('/v1/videos/generations/' + task)
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(15)
                    continue
                state = data.get('status', 'unknown')
                with LOCK:
                    row['state'] = state
                    save()
                if state == 'succeeded':
                    url = data.get('video_url') or (data.get('content') or {}).get('video_url')
                    raw = OUT / (sid + '-raw.mp4')
                    download(url, raw)
                    info = probe(raw)
                    dur = float(info['format']['duration'])
                    assert dur >= duration - 0.1, 'Short generated clip: stop rather than duplicate footage'
                    run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-an', '-vf', 'scale=848:480:force_original_aspect_ratio=increase,crop=848:480,setsar=1,fps=30', '-t', str(duration), '-c:v', 'libx264', '-crf', '19', '-pix_fmt', 'yuv420p', str(OUT / (sid + '.mp4'))])
                    for at, tag in [(0.4, 'start'), (duration/2, 'mid'), (duration-0.3, 'end')]:
                        run(['ffmpeg', '-y', '-v', 'error', '-ss', str(at), '-i', str(raw), '-frames:v', '1', str(OUT / (sid + '-' + tag + '.jpg'))])
                    with LOCK:
                        row.update(file=raw.name, actual_duration=dur, video_url=url)
                        save()
                    print('Complete', sid, dur, flush=True)
                    return
                if state in {'failed', 'cancelled', 'expired'}:
                    raise RuntimeError(str(data.get('error', state))[:500])
                time.sleep(15)
            raise RuntimeError('Poll timeout: preserve task id; no resubmit')
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                message = exc.read(1000).decode(errors='replace')
            else:
                message = str(exc)
            with LOCK:
                row.update(error=message.replace(key, '[REDACTED]')[:1000])
                save()
            raise RuntimeError('Shot ' + sid + ' stopped; see report') from None

    # Three concurrent requests; stop unstarted shots if either fails.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(generate, s) for s in SHOTS[:3]}
        remaining = iter(SHOTS[3:])
        while pending:
            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                f.result()
            for _ in done:
                shot = next(remaining, None)
                if shot:
                    pending.add(pool.submit(generate, shot))
    inputs = []
    for sid, _, _, _ in SHOTS:
        inputs += ['-i', str(OUT / (sid + '.mp4'))]
    inputs += ['-i', str(OUT / 'source.mp4')]
    filters = [f'[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]' for i in range(6)]
    filters.append(''.join(f'[v{i}]' for i in range(6))+'concat=n=6:v=1:a=0[v]')
    filters.append('[6:a]atrim=start=90:end=120,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.08,afade=t=out:st=29.4:d=0.6[a]')
    final = OUT / 'Drop_BlackRed_30s_Clean.mp4'
    run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]', '-t', '30', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(final)])
    info = probe(final)
    assert abs(float(info['format']['duration']) - 30) < 0.08
    assert any(s['codec_type'] == 'audio' for s in info['streams'])
    report['final'] = {'file': final.name, 'duration': info['format']['duration'], 'original_audio_preserved': True}
    save()
    print('FINAL READY', final, flush=True)

if __name__ == '__main__':
    main()
