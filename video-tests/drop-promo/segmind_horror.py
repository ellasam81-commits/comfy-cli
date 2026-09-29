"""One authorized ten-second horror insert; no paid retries."""
import json
import os
from pathlib import Path
import time
import requests
from segmind import SegmindClient

ROOT = Path(__file__).resolve().parent
OUT = Path('output/drop-horror')
HOST = 'https://api.segmind.com'

def main():
    assert os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1', 'Recover existing tasks; do not blindly rerun'
    key = os.environ['SEGMIND_API_KEY'].strip()
    assert key, 'SEGMIND_API_KEY not configured'
    headers = {'x-api-key': key}
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'model': 'seedance-2.0-mini', 'duration': 10, 'resolution': '480p', 'paid_submissions': 0}
    def save():
        (OUT/'report.json').write_text(json.dumps(report, indent=2))
    save()
    check = requests.get(HOST+'/v1/get-user-credits', headers=headers, timeout=45)
    check.raise_for_status()
    client = SegmindClient()
    upload = client.files.upload([ROOT/'refs/horror.jpg', ROOT/'refs/02.jpg'])
    urls = upload.get('file_urls') or []
    assert len(urls) == 2
    prompt = '''Create a genuinely frightening supernatural anime horror sequence, ten seconds, full-screen cinematic 16:9. Image 1 is the exact sinister flame-woman face and mirror entity design, image 2 establishes the same adult male with short wavy black hair and white angular geometric long coat. Keep identities and outfits. Black, deep crimson and ivory palette, harsh narrow red rim light, oppressive darkness, visible facial details. NO romance, no tender touching. No text, no split screen, no reference sheets.
Shot 1, seconds 0-4: medium close view from behind the adult man, trapped in a flooded gothic corridor. He abruptly looks over his shoulder in fear. In front of him the obsidian mirror slowly bends outward like breathing skin. Long black fingers creep out and grasp its external frame while a gigantic shadow rises. Camera creeps forward, water ripples flow backward.
Shot 2, seconds 4-10: sudden hard cut to image 1's terrifying female face filling the frame behind cracked glass, black empty eyes with tiny red pinprick pupils, ashen face, red-black burning hair. She is utterly still for one second; then her head tilts unnaturally, her closed-mouth smile grows slightly and her gaze turns directly toward the viewer. The claws tighten and glass cracks spread. At second 8.5 the mirror entity surges toward the camera, hair and black shadow whip outward, extreme close-up eyes, then darkness. Beautiful detailed anime horror, physical animated movement, no gore or wounds, no strobing.'''
    payload = dict(prompt=prompt,duration=10,resolution='480p',aspect_ratio='16:9',generate_audio=False,bitrate_mode='standard',seed=929991,reference_images=urls,skip_moderation=False)
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
                    (OUT/'horror-10s.mp4').write_bytes(media.content)
                    report['file']='horror-10s.mp4'
                    save()
                    print('VIDEO READY',flush=True)
                    return
            raise RuntimeError('No video URL in completed result')
    raise RuntimeError('Poll timeout; recover request without resubmitting')

if __name__=='__main__':
    main()
