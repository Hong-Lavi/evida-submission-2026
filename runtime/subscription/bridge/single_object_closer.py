"""Bounded syntax-only candidate; no bridge side effects or scientific validation."""
import hashlib,json,time
import jsonschema

class RepairRejected(ValueError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise RepairRejected('duplicate_key')
        out[k]=v
    return out

def _load(s):
    return json.loads(s,object_pairs_hook=_pairs,parse_constant=lambda _: (_ for _ in ()).throw(RepairRejected('nonfinite_number')))

def candidate(raw,schema,*,max_bytes=131072,max_candidates=2048,max_seconds=1.0):
    """Insert exactly one } outside strings; require unique schema-valid result.

    Caller must bind schema to actual registered function and preserve forced-tool
    checks. Limits may only be tightened. No already-valid JSON normalization.
    """
    if not isinstance(raw,str) or not isinstance(schema,dict):raise RepairRejected('invalid_input')
    if not 0<max_bytes<=131072 or not 0<max_candidates<=2048 or not 0<max_seconds<=1.0:raise RepairRejected('invalid_limits')
    started=time.monotonic();encoded=raw.encode('utf-8')
    if len(encoded)>max_bytes:raise RepairRejected('byte_limit')
    def deadline():
        if time.monotonic()-started>max_seconds:raise RepairRejected('time_limit')
    deadline()
    try:_load(raw)
    except json.JSONDecodeError as original:original_error={'message':original.msg,'character_offset':original.pos}
    else:raise RepairRejected('already_valid_json')
    # A missing object closer leaves precisely one unmatched object. Existing
    # mismatched closers may be the place needing insertion; do not reinterpret
    # strings, add array closers, or permit a second missing delimiter.
    quoted=False;escaped=False;positions=[];balance=0;array_balance=0
    for i,ch in enumerate(raw):
        deadline()
        if quoted:
            if escaped:escaped=False
            elif ch=='\\':escaped=True
            elif ch=='"':quoted=False
        elif ch=='"':quoted=True
        else:
            if ch=='{':balance+=1
            elif ch=='}':balance-=1
            elif ch=='[':array_balance+=1
            elif ch==']':array_balance-=1
            if ch in ',}]':positions.append(i)
        if len(positions)>max_candidates:raise RepairRejected('candidate_limit')
    if quoted or escaped or balance!=1 or array_balance!=0:raise RepairRejected('not_single_object_closer')
    positions.append(len(raw))
    if len(positions)>max_candidates:raise RepairRejected('candidate_limit')
    validator=jsonschema.Draft202012Validator(schema);validator.check_schema(schema);accepted=[]
    for pos in positions:
        deadline();repaired=raw[:pos]+'}'+raw[pos:]
        try:value=_load(repaired)
        except (json.JSONDecodeError,RepairRejected):continue
        deadline()
        if not validator.is_valid(value):continue
        deadline();accepted.append((pos,repaired,value))
        if len(accepted)>1:raise RepairRejected('ambiguous_repair')
    deadline()
    if len(accepted)!=1:raise RepairRejected('no_unique_schema_valid_repair')
    pos,repaired,value=accepted[0];assert repaired[:pos]+repaired[pos+1:]==raw
    h=lambda b:hashlib.sha256(b).hexdigest()
    receipt={'status':'UNIQUE_SINGLE_OBJECT_CLOSER_CANDIDATE','original_sha256':h(encoded),'repaired_sha256':h(repaired.encode()),'schema_sha256':h(json.dumps(schema,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),'original_parse_error':original_error,'operation':{'insert':'}','character_offset':pos,'utf8_byte_offset':len(raw[:pos].encode())},'candidate_positions_tested':len(positions),'elapsed_seconds':time.monotonic()-started,'limits':{'max_bytes':max_bytes,'max_candidates':max_candidates,'max_seconds':max_seconds},'duplicate_keys_rejected':True,'remove_inserted_byte_restores_original':True,'scientific_acceptance':'NOT_ASSESSED','original_failure_preserved':True}
    return repaired,value,receipt

def candidate_bounded(raw,schema,**limits):
    """Exec a pure worker; subprocess.run kills/waits its own child on timeout."""
    import subprocess,sys,pathlib
    if not isinstance(raw,str) or not isinstance(schema,dict):raise RepairRejected('invalid_input')
    if len(raw.encode('utf-8'))>131072:raise RepairRejected('byte_limit')
    schema_wire=json.dumps(schema,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(schema_wire.encode('utf-8'))>1048576:raise RepairRejected('schema_byte_limit')
    request=json.dumps({'raw':raw,'schema':schema,'limits':limits},ensure_ascii=False,allow_nan=False)
    try:
        result=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve()),'--worker'],
            input=request,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            encoding='utf-8',timeout=4.0,check=False)
    except subprocess.TimeoutExpired:raise RepairRejected('worker_wall_time_limit') from None
    except (OSError,ValueError):raise RepairRejected('worker_start_failed') from None
    if result.returncode!=0:raise RepairRejected('worker_failed')
    if len(result.stdout.encode('utf-8'))>2097152:raise RepairRejected('worker_output_limit')
    try:
        reply=_load(result.stdout)
        if not isinstance(reply,dict) or set(reply)!={'status','result'}:raise ValueError()
        if reply['status']!='ok':raise RepairRejected('worker_rejected')
        recovered,value,receipt=reply['result']
        pos=receipt['operation']['character_offset']
        if not isinstance(pos,int) or not isinstance(recovered,str) or recovered[:pos]+recovered[pos+1:]!=raw or recovered[pos:pos+1]!='}':raise ValueError()
        if _load(recovered)!=value:raise ValueError()
        return recovered,value,receipt
    except RepairRejected:raise
    except (ValueError,KeyError,TypeError,IndexError):raise RepairRejected('malformed_worker_reply') from None

def _worker_main():
    import sys
    try:
        wire=sys.stdin.buffer.read(2500001)
        if len(wire)>2500000:raise RepairRejected('worker_input_limit')
        request=_load(wire.decode('utf-8'))
        result=candidate(request['raw'],request['schema'],**request['limits'])
        reply={'status':'ok','result':result}
    except Exception:
        reply={'status':'rejected','result':None}
    # IPC only; no raw schema/text/error is written to diagnostic stderr.
    sys.stdout.write(json.dumps(reply,ensure_ascii=False,allow_nan=False,separators=(',',':')))

def strict_load(raw):
    """Reject duplicate keys/nonfinite numbers in valid originals too."""
    return _load(raw)


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--worker']:_worker_main()
    else:raise SystemExit(2)
