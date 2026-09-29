"""One authorized four-second expression replacement; no paid retries."""
import json
import os
from pathlib import Path
import time
import requests
from segmind import SegmindClient

ROOT = Path(__file__).resolve().parent
OUT = Path('output/drop-expression')
HOST = 'https://api.segmind.com'

def main():
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'Recover existing tasks; do not blindly rerun'
    key = os.environ['SEGMIND_API_KEY'].strip()
    assert key, 'SEGMIND_API_KEY not configured'
    headers = {'x-api-key': key}
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'model': 'seedance-2.0-mini', 'duration': 4, 'resolution': '480p', 'paid_submissions': 0}
    def save():
        (OUT/'report.json').write_text(json.dumps(report, indent=2))
    save()
    check = requests.get(HOST+'/v1/get-user-credits', headers=headers, timeout=45)
    check.raise_for_status()
    client = SegmindClient()
    upload = client.files.upload([ROOT/'refs/male-eerie.jpg'])
    urls = upload.get('file_urls') or []
    assert len(urls) == 1
    prompt = """Animate this exact anime frame for four seconds. Preserve the same handsome adult male facial identity, wavy short black hair, white angular geometric coat, over-the-shoulder framing, ornate black mirror and flooded gothic hall. His expression stays eerily calm and knowing throughout: closed mouth, subtle asymmetric smile, slightly narrowed steady eyes, relaxed eyebrows. Absolutely never show fright, surprise, raised eyebrows, a gasp, wide eyes or an open mouth. He very slowly tilts his head toward the viewer by a few degrees while the tiny smile deepens almost imperceptibly; his gaze follows the lens. His coat edge and hair move gently. Behind him the mirror surface slowly bulges and the reflection lags unnaturally, red candlelight shivers and ripples flow inward. Slow subtle camera push-in. Black and dark red supernatural horror atmosphere, restrained creepy performance, no dialogue, no text, no extra characters, no scene cuts, no style change."""
    payload = dict(prompt=prompt,duration=4,resolution='480p',aspect_ratio='16:9',generate_audio=False,bitrate_mode='standard',seed=929993,first_frame_url=urls[0],skip_moderation=False)
    report['paid_submissions'] = 1
    report['state'] = 'SUBMITTING'
    save()
    response = requests.post(HOST+'/v2/seedance-2.0-mini',headers=headers,json=payload,timeout=120)
    if not response.ok:
        report.update(state='REJECTED', error=response.text[:1200].replace(key,'[REDACTED]'))
        save()
        response.raise_for_status()
    data=response.json()
    rid=data['request_id']
    report.update(request_id=rid,state=data.get('status','QUEUED'))
    save()
    print('Accepted request',rid,flush=True)
    for _ in range(200):
        time.sleep(10)
        response=requests.get(HOST+'/v2/requests/'+rid+'/status',headers=headers,timeout=60)
        data=response.json()
        state=data.get('status','UNKNOWN')
        report['state']=state
        save()
        if state=='FAILED':
            report['error']=str(data)[:1500].replace(key,'[REDACTED]')
            save()
            raise RuntimeError('Generation failed; see report')
        response.raise_for_status()
        if state=='COMPLETED':
            result=requests.get(HOST+'/v2/requests/'+rid,headers=headers,timeout=60)
            result.raise_for_status()
            data=result.json()
            (OUT/'result.json').write_text(json.dumps(data,indent=2))
            found=[]
            def collect(x):
                if isinstance(x,str) and x.startswith('https://'): found.append(x)
                elif isinstance(x,dict):
                    for v in x.values(): collect(v)
                elif isinstance(x,list):
                    for v in x: collect(v)
            collect(data.get('output',data))
            for url in dict.fromkeys(found):
                media=requests.get(url,timeout=240)
                media.raise_for_status()
                if media.content[4:8]==b'ftyp' or 'video/' in media.headers.get('content-type',''):
                    (OUT/'male-eerie-4s.mp4').write_bytes(media.content)
                    report['file']='male-eerie-4s.mp4'
                    save()
                    print('VIDEO READY',flush=True)
                    return
            raise RuntimeError('No video URL in completed result')
    raise RuntimeError('Poll timeout; recover request without resubmitting')

if __name__=='__main__':
    main()
