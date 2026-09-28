"""Seven authorized WAN clips; never retry a paid creation request."""
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
OUT = Path('output/tanhuo-mv')
HOST = 'https://api.xrtoken.ai'
SOURCE = 'https://cdn.creativeclaw.co/u/b3866ea4/videos/1a62c1c7-1e8a-4cc1-bd06-89f9322f9d5c.mp4'
LOCK = threading.RLock()
COMMON = '''Create a fully animated cinematic 2D anime fantasy romance music-video scene, ten seconds, 16:9. Image 1 supplies this scene's composition and emotion. Image 2 locks the same two ADULT characters throughout: handsome short wavy black-haired man with black high collar, white sharply angular architectural shoulder long coat and black-white trousers; flame spirit woman Tanhuo with gentle amber eyes, long flowing orange-gold flame hair and opaque burgundy-red floor-length dress edged with golden fire. Preserve exact faces, costume, anatomy, hair and body proportions. Hand-painted lavish theatrical anime, fine linework, luminous painterly backgrounds, dramatic depth, ice-blue and warm amber contrast. Both faces remain unmistakably anime. The same frozen lake, floating crystal islands and luminous sky connect all scenes. Real character movement and expressive restrained acting, breathing, blinking, moving hands, hair, flame and fabric; not a still-image zoom or slideshow. No dialogue, singing, lip movement, captions, lettering, logos, panel borders, duplicate characters, new people, abrupt morphing, costume changes or live action. Keep bodies intact, natural hands and consistent eye lines. Flame is gentle magical warmth, never burns skin. Silent output; the original continuous song will be added later. One camera move, coherent physical progression, no sudden cuts inside the shot. End with one second of continuing subtle movement for transition. '''
SHOTS = [
    ('01', '01', 'AWAKENING. Only the man is physically present. Wide to medium slow tracking approach: he takes three natural steps on the moonlit frozen lake, notices a glowing ember drifting toward him, stops and cups it in both hands. The little flame rises and curls; his lonely eyes brighten with wonder. Blue crystal islands remain distant and stable. The woman does NOT appear yet. Image 2 is identity only, do not add her.'),
    ('02', '02', 'MEETING. The woman is now standing opposite the man, both full adult bodies intact and separate. Begin with them two paces apart on the same blue moonlit lake. She takes a tentative step toward him, flame hair flows behind her, tiny golden sparks drift between them. He lowers his empty hands, meets her eyes and smiles softly; she responds shyly. Slow gentle clockwise camera arc ending in a medium two-shot. No transformation or disappearance.'),
    ('03', '03', 'CHOOSING TRUST. Medium intimate two-shot. A small flame curls around her right fingertips. She worries she may hurt him and draws her hand back toward her chest, glancing down. He slowly offers his open left palm and waits. She looks into his eyes, then deliberately places her right hand gently into his left. Their joined hands are safe; both relax and smile. Camera slowly pushes closer. Show the hand connection clearly without extra fingers. Keep the man on screen right, woman on left.'),
    ('04', '04', 'RUNNING TOGETHER. Both characters already holding hands. Sideways tracking wide shot as they run steadily together across the flat frozen lake, man at frame left and woman at right, both moving toward frame right. Footfalls contact solid ice naturally; no floating. Her flame train releases tiny glowing birds that fly ahead, his white coat and her red dress trail in the same wind. They exchange a delighted glance while continuing forward. End as they gently slow and see soft snow beginning. No stairs, no bridge collapse, no combat.'),
    ('05', '05', 'SHELTER. Snow falls softly on the same lake; the couple has stopped. Her flame hair is still bright and intact but a small flame held between her cupped hands flickers. She looks worried. The man steps closer and gently places his hands around the outside of hers to shelter that little flame from the wind, then curves his shoulders toward her. She looks up with relieved shining eyes and a subtle smile. Snow continues drifting; warm light gradually strengthens on both faces. Slow intimate dolly-in. No sacrifice, injury, fading body, or extinguished hair.'),
    ('06', '05', 'RECIPROCAL LOVE. Continue with the same pair sheltering a little flame between their hands, close and safe in gentle snow. The man smiles reassuringly; she leans her forehead softly against his, they close their eyes briefly, then open them with peaceful smiles. The sheltered flame brightens and releases warm floating flower petals. As they look toward the horizon together, snow slows and pink dawn light appears behind them. Slow pullback from medium close-up to waist-up. Both remain fully present. Natural joined hands, no kissing required, no tears of grief.'),
    ('07', '06', 'A WORLD IN BLOOM, HAPPY ENDING. Wide three-quarter rear view of the same two intact adult characters, man left, woman right, hand in hand at the lake edge at peach-gold sunrise. They take three slow steps toward the light; white and peach flowers unfurl sequentially beside their feet and across the shore, golden petals rise over clear reflective water. Camera cranes gently upward and back to reveal crystal islands and the flowering lake. Her orange flame hair and red dress remain, his black-white angular coat remains. They turn their faces briefly toward each other with affectionate smiles, then face the dawn together. End in serene continuing natural motion, never freeze.'),
]

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
    assert len(SHOTS) == 7
    assert all((ROOT / 'refs' / (ref + '.jpg')).is_file() for _, ref, _ in SHOTS)
    if not args.execute:
        print('VALID: seven 10s clips, 70 paid seconds maximum, 67s final; original music; no paid retries')
        return
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'Do not blindly rerun paid jobs'
    key = os.environ['XRTOKEN'].strip()
    assert key
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / 'report.json'
    assert not report_path.exists(), 'Existing report: recover tasks rather than resubmit'
    report = {'model': 'wan3.0-video', 'resolution': '480P', 'max_paid_seconds': 70, 'target_duration': 67, 'clips': []}

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
        sid, ref, action = shot
        row = {'id': sid, 'state': 'SUBMITTING', 'requested_duration': 10}
        with LOCK:
            report['clips'].append(row)
            save()
        content = [{'type': 'text', 'text': COMMON + action}]
        for r in [ref, '02']:
            content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode((ROOT / 'refs' / (r + '.jpg')).read_bytes()).decode()}, 'role': 'reference_image'})
        payload = {'model': 'wan3.0-video', 'duration': 10, 'resolution': '480P', 'ratio': '16:9', 'generate_audio': False, 'watermark': False, 'prompt_extend': False, 'seed': 929100 + int(sid), 'content': content}
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
                    assert dur >= 9.9, 'Short generated clip: stop rather than duplicate footage'
                    run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-an', '-vf', 'scale=848:480:force_original_aspect_ratio=increase,crop=848:480,setsar=1,fps=30', '-t', '10', '-c:v', 'libx264', '-crf', '19', '-pix_fmt', 'yuv420p', str(OUT / (sid + '.mp4'))])
                    for at, tag in [(0.5, 'start'), (5, 'mid'), (9.4, 'end')]:
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

    # Two concurrent requests; stop unstarted shots if either fails.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(generate, s) for s in SHOTS[:2]}
        remaining = iter(SHOTS[2:])
        while pending:
            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                f.result()
            for _ in done:
                shot = next(remaining, None)
                if shot:
                    pending.add(pool.submit(generate, shot))
    inputs = []
    for sid, _, _ in SHOTS:
        inputs += ['-i', str(OUT / (sid + '.mp4'))]
    inputs += ['-i', str(OUT / 'source.mp4')]
    filters = [f'[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]' for i in range(7)]
    previous = 'v0'
    for i in range(1, 7):
        label = 'x' + str(i)
        filters.append(f'[{previous}][v{i}]xfade=transition=fade:duration=0.5:offset={9.5*i}[{label}]')
        previous = label
    filters.append('[7:a]apad=whole_dur=67,atrim=duration=67,asetpts=PTS-STARTPTS[a]')
    final = OUT / 'Tanhuo_With_You_67s.mp4'
    run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[' + previous + ']', '-map', '[a]', '-t', '67', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(final)])
    info = probe(final)
    assert abs(float(info['format']['duration']) - 67) < 0.08
    assert any(s['codec_type'] == 'audio' for s in info['streams'])
    report['final'] = {'file': final.name, 'duration': info['format']['duration'], 'original_audio_preserved': True}
    save()
    print('FINAL READY', final, flush=True)

if __name__ == '__main__':
    main()
