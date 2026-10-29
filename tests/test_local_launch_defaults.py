"""Parse only normal CLI setup; never execute credential/model/runtime launch code."""
import argparse,ast,importlib.util,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1]

def parse(name,argv):
 tree=ast.parse((P/name).read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
 body=[]
 for n in main.body:
  body.append(n)
  if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Attribute)and n.value.func.attr=='parse_args':break
 else:raise AssertionError('No parse_args boundary')
 body.append(ast.Return(value=ast.Name(id='args',ctx=ast.Load())))
 tiny=ast.Module(body=[ast.FunctionDef(name='parse_only',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=body,decorator_list=[])],type_ignores=[])
 ast.fix_missing_locations(tiny);ctx={'argparse':argparse,'Path':Path,'__doc__':'CLI parsing fixture'}
 exec(compile(tiny,'parse-only','exec'),ctx)
 with patch.object(sys,'argv',['fixture',*argv]):return ctx['parse_only']()
class Defaults(unittest.TestCase):
 def test_all_four_cli_defaults_are_approved_public_profile(self):
  for name in ['evida/server.py','evida/transport_probe.py','scripts/run_product.py','scripts/api_probe.py']:
   with self.subTest(name=name):
    args=parse(name,['--credential-file','/synthetic/credential'] if name=='evida/transport_probe.py'else []);self.assertEqual((args.model,args.effort),('gpt-6-sol','medium'))
    args=parse(name,(['--credential-file','/synthetic/credential']if name=='evida/transport_probe.py'else [])+['--model','gpt-5.6-sol','--effort','high']);self.assertEqual((args.model,args.effort),('gpt-5.6-sol','high'))
 def test_application_default_aligned_without_changing_explicit_parameter(self):
  tree=ast.parse((P/'evida/server.py').read_text());app=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Application');init=next(n for n in app.body if isinstance(n,ast.FunctionDef)and n.name=='__init__');defaults=dict(zip([n.arg for n in init.args.args][-len(init.args.defaults):],init.args.defaults))
  self.assertEqual(ast.literal_eval(defaults['model']),'gpt-6-sol');self.assertEqual(ast.literal_eval(defaults['effort']),'medium')
 def test_api_probe_payload_keeps_allowlist_and_explicit_medium_without_network(self):
  f=P/'scripts/api_probe.py';spec=importlib.util.spec_from_file_location('probe203',f);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  policy={'base_url':'https://dacon-apim-hackathon-0903.azure-api.net/hackathon/openai/v1','allowed_models':['gpt-6-sol','gpt-5.6-sol'],'development_api_models':['gpt-6-sol']}
  req=m.build_request(policy,'SYNTHETIC_OFFLINE_VALUE','gpt-6-sol');wire=json.loads(req.data)
  self.assertEqual(wire['model'],'gpt-6-sol');self.assertEqual(wire['reasoning']['effort'],'medium')
  for model in ['unknown','gpt-5.6-sol']:
   with self.assertRaises(ValueError):m.build_request(policy,'SYNTHETIC_OFFLINE_VALUE',model)
  with self.assertRaises(ValueError):m.build_request(policy,'SYNTHETIC_OFFLINE_VALUE','gpt-6-sol','invalid')
  self.assertEqual(m.NoRedirect().redirect_request(None,None,None,None,None,None),None)
if __name__=='__main__':unittest.main(verbosity=2)
