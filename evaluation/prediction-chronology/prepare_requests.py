#!/usr/bin/env python3
"""Restore exact frozen requests locally; never invoke a provider."""
import argparse,hashlib,json
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-packet',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
 root=Path(__file__).resolve().parent;source_bytes=a.source_packet.read_bytes();descriptor=json.loads((root/'source-descriptor.json').read_text())
 assert hashlib.sha256(source_bytes).hexdigest()==descriptor['original_file_sha256'],'Original packet hash mismatch: approximate reconstruction is not an exact replay input'
 source=json.loads(source_bytes);semantics=json.loads((root/'transport-semantics.json').read_text());a.out.mkdir(parents=True,exist_ok=False)
 outputs=[]
 for i in range(1,19):
  b=f'B{i:02}';call=root/'records/attempt-03/component-calls'/b;req=json.loads((call/'request.json').read_text());req['source_packet']=source
  data=(json.dumps(req,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode();receipt=json.loads((call/'receipt.json').read_text());digest=hashlib.sha256(data).hexdigest()
  assert digest==receipt['request_sha256'];(a.out/(b+'.request.json')).write_bytes(data);outputs.append({'blind_id':b,'original_request_sha256':digest})
 (a.out/'transport-semantics.json').write_text(json.dumps(semantics,ensure_ascii=False,indent=2)+'\n')
 (a.out/'restoration-receipt.json').write_text(json.dumps({'status':'PASS','restored_requests':outputs,'model_calls':0},indent=2)+'\n')
 print(json.dumps({'status':'PASS','byte_identical_requests':18,'model_calls':0}))
if __name__=='__main__':main()
