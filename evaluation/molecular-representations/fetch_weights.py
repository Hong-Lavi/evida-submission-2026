"""Explicit official download with size/SHA verification; never invoked by verification."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pin=json.loads((Path(__file__).resolve().parent/'weights.json').read_text())
    if args.out.exists():raise FileExistsError(args.out)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.out.with_name(args.out.name+'.partial')
    with urllib.request.urlopen(pin['download_url'],timeout=120) as source,temporary.open('xb') as output:
        while chunk:=source.read(1024*1024):output.write(chunk)
    if temporary.stat().st_size!=pin['size_bytes'] or hashlib.sha256(temporary.read_bytes()).hexdigest()!=pin['sha256']:
        raise ValueError('Weight verification failed; partial download retained, not used')
    temporary.rename(args.out)
    print(json.dumps({'status':'VERIFIED','sha256':pin['sha256'],'size_bytes':pin['size_bytes']}))
