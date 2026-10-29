"""Fixed internal CPU worker; no user executable or user path selection."""
from pathlib import Path
import base64
import json
import sys
from .pocket_docking import _execute,_progress
incoming,output=map(Path,sys.argv[1:]);p=json.loads(incoming.read_text());binding=p['binding']
_progress(output.parent/'progress.json',{'status':'preparing_receptor_and_docking','rows':[],'selected_pocket_id':binding['geometry']['pocket_id']})
try:
    result=_execute(base64.b64decode(p['content_base64'],validate=True),p['meta'],binding,output.parent/'author')
except Exception as exc:result={'status':'failed','error_type':type(exc).__name__,'error':str(exc)[:1500],'rows':[]}
tmp=output.with_suffix('.part');tmp.write_text(json.dumps(result,ensure_ascii=False));tmp.replace(output)
