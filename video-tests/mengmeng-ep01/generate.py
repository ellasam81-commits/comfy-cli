"""Generate EP01 once via XRToken; never retry paid submissions."""
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
OUT = Path('output/mengmeng-ep01')
HOST = 'https://api.xrtoken.ai'


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def ass_time(t):
    return f'{int(t)//3600}:{int(t)//60%60:02}:{int(t)%60:02}.{int(round(t*100))%100:02}'


def edit(cfg, report):
    parts = []
    for row in report['clips']:
        src = OUT / row['file']
        info = probe(src)
        if not any(s['codec_type'] == 'audio' for s in info['streams']):
            raise RuntimeError(f"Clip {row['id']} has no audio track; refuse delivery")
        row['actual_duration'] = float(info['format']['duration'])
        target = OUT / f"{row['id']}-normalized.mp4"
        run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf',
             'scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,tpad=stop_mode=clone:stop_duration=5',
             '-af', 'apad', '-t', '5', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
             '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(target)])
        parts.append(target)
    concat = OUT / 'concat.txt'
    concat.write_text(''.join(f"file '{p.resolve()}'\n" for p in parts))
    joined = OUT / 'joined.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat), '-c', 'copy', str(joined)])
    headers = '''[Script Info]
ScriptType: v4.00+
PlayResX: 854
PlayResY: 480
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Noto Sans CJK SC,23,&H00FFFFFF,&H00FFFFFF,&H00181818,&H80000000,0,0,0,0,100,100,0,0,1,1.8,0,2,32,32,17,1
Style: Title,Noto Sans CJK SC,20,&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,1.6,0,7,22,22,18,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events = ['Dialogue: 0,0:00:00.00,0:00:02.80,Title,,0,0,0,,萌萌谈与全城精灵 · EP01\\N{\\fs13}猫说我被投诉了417次 | 作者：林爱丽']
    for i, clip in enumerate(cfg['clips']):
        if clip['zh']:
            label = clip['speaker'] + '：' + clip['zh']
            events.append(f"Dialogue: 0,{ass_time(i*5+0.15)},{ass_time(i*5+4.8)},Main,,0,0,0,,{label}\\N{{\\fs15}}{clip['en']}")
    ass = OUT / 'subtitles.ass'
    ass.write_text(headers + '\n'.join(events) + '\n')
    final = OUT / 'Mengmeng_EP01_60s_ZH_EN.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(joined), '-vf', f"ass={ass}", '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(final)])
    report['final_file'] = final.name
    report['final_duration'] = float(probe(final)['format']['duration'])
    report['qa_status'] = 'requires_visual_and_dialogue_review'
    for row in report['clips']:
        run(['ffmpeg', '-y', '-v', 'error', '-ss', '2.5', '-i', str(OUT / row['file']), '-frames:v', '1', str(OUT / (row['id'] + '-preview.jpg'))])


def main():
    cfg = json.loads((ROOT / 'episode.json').read_text())
    assert len(cfg['clips']) == 12 and sum(c['duration'] for c in cfg['clips']) == 60
    assert cfg['model'] == 'wan3.0-video' and cfg['resolution'] == '480P'
    assert (ROOT / 'reference.jpg').is_file()
    if os.environ.get('MENGMENG_EXECUTE') != '1':
        print('Dry run passed: 12 x 5s, 480P, audio on, no paid requests.')
        return
    if os.environ.get('GITHUB_RUN_ATTEMPT', '1') != '1':
        raise RuntimeError('Refuse paid rerun. Recover existing task IDs instead.')
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'report.json').exists():
        raise RuntimeError('Report already exists: refuse duplicate submissions.')
    key = os.environ['XRTOKEN'].strip()
    if not key:
        raise RuntimeError('Missing XRTOKEN secret')
    report = {'episode': 1, 'provider': 'XRToken', 'model': cfg['model'], 'max_paid_seconds': 60, 'clips': []}
    ref = 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'reference.jpg').read_bytes()).decode()

    def save():
        temp = OUT / 'report.tmp'
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        temp.replace(OUT / 'report.json')

    def request(path, body=None):
        headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(HOST + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)

    def error(exc):
        result = {'error_type': type(exc).__name__}
        if isinstance(exc, urllib.error.HTTPError):
            result['http_status'] = exc.code
            result['message'] = exc.read(1500).decode(errors='replace').replace(key, '[REDACTED]')
        return result

    def submit(clip):
        row = {'id': clip['id'], 'state': 'SUBMITTING', 'duration': 5}
        report['clips'].append(row)
        save()
        body = {'model': cfg['model'], 'content': [
            {'type': 'text', 'text': clip['prompt']},
            {'type': 'image_url', 'image_url': {'url': ref}, 'role': 'reference_image'}],
            'duration': 5, 'resolution': '480P', 'ratio': '16:9', 'generate_audio': True,
            'watermark': False, 'prompt_extend': False, 'seed': 927001}
        try:
            res = request('/v1/videos/generations', body)
            task = res.get('id') or res.get('data', {}).get('id')
            if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+', task):
                raise RuntimeError('Missing task ID; never blindly resubmit.')
            row.update(task_id=task, state=res.get('status', 'queued'))
            print('Accepted clip', clip['id'], task, flush=True)
            save()
            return True
        except Exception as exc:
            row.update(state='SUBMISSION_UNKNOWN_OR_FAILED', **error(exc))
            save()
            print('Submission stopped:', json.dumps(row, ensure_ascii=False), flush=True)
            return False

    def poll(rows):
        pending = list(rows)
        deadline = time.monotonic() + 2100
        while pending and time.monotonic() < deadline:
            for row in list(pending):
                try:
                    res = request('/v1/videos/generations/' + urllib.parse.quote(row['task_id'], safe=''))
                    row['state'] = res.get('status', 'unknown')
                    if row['state'] == 'succeeded':
                        content = res.get('content') or {}
                        url = res.get('video_url') or (content.get('video_url') if isinstance(content, dict) else None)
                        if not url or urllib.parse.urlparse(url).scheme != 'https':
                            raise RuntimeError('No valid video URL')
                        row['video_url'] = url
                        path = OUT / (row['id'] + '-raw.mp4')
                        with urllib.request.urlopen(url, timeout=180) as media:
                            path.write_bytes(media.read())
                        row['file'] = path.name
                        pending.remove(row)
                        print('Downloaded clip', row['id'], flush=True)
                    elif row['state'] in {'failed', 'cancelled', 'expired'}:
                        row['error'] = str(res.get('error', ''))[:1200].replace(key, '[REDACTED]')
                        pending.remove(row)
                        print('Generation failed', row['id'], row['error'], flush=True)
                except Exception as exc:
                    row['last_poll_error'] = error(exc)
                save()
            if pending:
                time.sleep(15)
        save()
        return all('file' in row for row in rows)

    save()
    # Verify authentication without submitting a paid job.
    try:
        request('/v1/videos/generations?limit=1')
    except Exception as exc:
        report['preflight_error'] = error(exc)
        save()
        raise SystemExit(2)
    # First purchased shot is part of the final episode, not an extra paid test.
    if not submit(cfg['clips'][0]) or not poll(report['clips'][:1]):
        raise SystemExit(2)
    if not any(s['codec_type'] == 'audio' for s in probe(OUT / report['clips'][0]['file'])['streams']):
        report['stop_reason'] = 'First shot missing audio. No more clips submitted.'
        save()
        raise SystemExit(2)
    for start in range(1, 12, 3):
        batch = cfg['clips'][start:start+3]
        accepted = []
        ok = True
        for clip in batch:
            if not submit(clip):
                ok = False
                break
            accepted.append(report['clips'][-1])
        complete = poll(accepted)
        if not ok or not complete:
            raise SystemExit(2)
    edit(cfg, report)
    save()
    print('60-second edit assembled. Awaiting visual/dialogue review.', flush=True)


if __name__ == '__main__':
    main()
