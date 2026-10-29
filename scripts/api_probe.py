"""One bounded gateway check. Offline by default; never prints credentials."""
import argparse, json, os, sys, time
import urllib.error, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def build_request(policy,key,model,effort="medium"):
    if model not in policy['allowed_models']:raise ValueError('Model is outside the competition allowlist')
    if model not in policy.get('development_api_models', policy['allowed_models']):
        raise ValueError('Model is outside the current approved development policy')
    if effort not in ('medium','high','xhigh','max'):raise ValueError('Unapproved reasoning effort')
    endpoint=policy['base_url']+'/responses'
    if endpoint!='https://dacon-apim-hackathon-0903.azure-api.net/hackathon/openai/v1/responses':
        raise ValueError('Unapproved API destination')
    if not key or key.strip()!=key:raise ValueError('Missing or malformed key')
    body=json.dumps({'model':model,'reasoning':{'effort':effort},'input':'Reply only OK','max_output_tokens':128}).encode()
    return urllib.request.Request(endpoint,data=body,method='POST',headers={'Content-Type':'application/json','api-key':key})

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--model',default='gpt-6-sol');p.add_argument('--effort',default='medium',choices=['medium','high','xhigh','max']);p.add_argument('--credential-file',type=Path)
    args=p.parse_args();policy=json.loads((ROOT/'configs/api_policy.json').read_text())
    if args.model not in policy['allowed_models']:p.error('Model is outside the competition allowlist')
    if args.model not in policy.get('development_api_models', policy['allowed_models']):
        p.error('Model is outside the current approved development policy')
    if not args.live:
        build_request(policy,'OFFLINE_TEST_VALUE',args.model,args.effort)
        for forbidden in ['gpt-6-astra','unknown']:
            try:build_request(policy,'OFFLINE_TEST_VALUE',forbidden)
            except ValueError:pass
            else:raise AssertionError('Allowlist failed')
        try:build_request(policy,'',args.model)
        except ValueError:pass
        else:raise AssertionError('Credential boundary failed')
        print(json.dumps({'offline_config_checks':'PASS','network_calls':0,'credentials_loaded':False}))
        return 0
    if not args.credential_file:p.error('--live requires an owner-only --credential-file')
    sys.path.insert(0,str(ROOT))
    from evida.local_credential import read_owner_credential, reject_credential_environment
    reject_credential_environment()
    key=read_owner_credential(args.credential_file)
    request=build_request(policy,key,args.model,args.effort)
    del key
    started=time.monotonic();record={'mode':'LIVE','requested_model':args.model,'requested_effort':args.effort,'attempts':1}
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=60) as response:
            result=json.load(response)
            record['http_status']=response.status
            record['actual_model']=result.get('model')
            record['response_status']=result.get('status')
            record['usage']=result.get('usage')
            record['gateway']={k:response.headers.get(k) for k in policy['usage_headers']}
            record['response_id']=result.get('id')
            actual=result.get('model','')
            record['model_identity_matches']=actual==args.model or actual.startswith(args.model+'-')
            record['completed']=result.get('status')=='completed'
            ok=record['model_identity_matches'] and record['completed']
    except urllib.error.HTTPError as exc:
        record['http_status']=exc.code
        record['retry_after']=exc.headers.get('Retry-After')
        record['outcome']={401:'AUTH',403:'TOTAL_QUOTA',429:'RATE_LIMIT',400:'REQUEST_OR_MODEL',404:'REQUEST_OR_MODEL'}.get(exc.code,'HTTP_ERROR')
        ok=False
    except (urllib.error.URLError,TimeoutError,ValueError) as exc:
        record['outcome']=type(exc).__name__;record['billing_outcome']='UNKNOWN';ok=False
    record['elapsed_seconds']=round(time.monotonic()-started,3)
    # Small metadata only; never persist request, auth headers, input, or model text.
    out=ROOT/'audit';out.mkdir(exist_ok=True)
    path=out/('api-probe-'+str(time.time_ns())+'.json')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2)
    print(json.dumps(record));return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
