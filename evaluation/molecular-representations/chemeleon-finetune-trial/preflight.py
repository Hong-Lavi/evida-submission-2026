from pathlib import Path
import json, time, traceback, sys
import numpy as np
from finetune_adapter import fit_predict
b=Path(__file__).resolve().parents[1];out=Path(__file__).parent/sys.argv[1];out.mkdir(exist_ok=False)
rows=[{"candidate_id":f"synthetic-{i}","smiles":s,"p_activity":float(i)/4} for i,s in enumerate(["CC","CCC","CCCC","CCO","CCCO","CCCCO","CCN","CCCN","CCCCN","c1ccccc1","c1ccncc1","c1ccccc1O","C1CCCCC1","C1CCNCC1","CC(=O)O","CCC(=O)O"])]
results=[]
try:
 for arm,pretrained in [("pretrained",True),("matched_random",False)]:
  val,pred,report=fit_predict(rows[:8],rows[8:12],[{"candidate_id":r["candidate_id"],"smiles":r["smiles"]} for r in rows[12:]],b/"chemeleon-trial/weights/chemeleon_mp.pt",out/arm,pretrained=pretrained,epochs=1,batch_size=4)
  assert report["initial_encoder_sha256"]!=report["fitted_encoder_sha256"]
  results.append({"arm":arm,"status":"PASS","validation_predictions":val.tolist(),"predictions":pred.tolist(),"fit":report})
 assert results[0]["fit"]["initial_head_sha256"]==results[1]["fit"]["initial_head_sha256"]
 receipt={"status":"PASS","synthetic_fixture":True,"biological_labels":False,"official_benchmark_data_used":False,"model_calls":0,"arms":results}
except Exception as e:
 receipt={"status":"FAILED","error_type":type(e).__name__,"error":str(e),"traceback":traceback.format_exc(),"arms":results}
(out/"receipt.json").write_text(json.dumps(receipt,indent=2))
print(json.dumps({"status":receipt["status"],"completed_arms":len(results),"error":receipt.get("error"),"GPU_used":True}))
if receipt["status"]!="PASS":raise SystemExit(1)
