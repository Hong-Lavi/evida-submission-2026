"""Fake-canary local CLI tests: no private credentials, exec, provider or network calls."""
import contextlib,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P))
import evida

from evida import local_credential as c
spec=importlib.util.spec_from_file_location('launch203',P/'scripts/run_product.py');launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
CANARY='SYNTHETIC_ONLY_LOCAL_CANARY_203'
class Credentials(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.private=Path(self.tmp.name)/'.secrets';self.private.mkdir(mode=0o700);self.key=self.private/'canary';self.key.write_text(CANARY);self.key.chmod(0o600)
 def tearDown(self):self.tmp.cleanup()
 def test_check_inspects_metadata_without_reading_credential_bytes(self):
  with patch.object(c.os,'read',side_effect=AssertionError('must not read bytes')):
   self.assertEqual(c.inspect_owner_credential(self.key),self.key)
  capture=io.StringIO()
  with patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['launch','--check','--key-file',str(self.key)]),patch.object(Path,'read_text',side_effect=AssertionError('no body reads')),contextlib.redirect_stdout(capture):launch.main()
  result=json.loads(capture.getvalue());self.assertFalse(result['credential_bytes_read']);self.assertEqual(result['network_calls'],0);self.assertNotIn(CANARY,capture.getvalue())
 def test_normal_server_receives_credential_in_memory_without_provider_dispatch(self):
  spec=importlib.util.spec_from_file_location('evida._server203',P/'evida/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
  from unittest.mock import MagicMock
  app=MagicMock();http=MagicMock();http.serve_forever.side_effect=KeyboardInterrupt
  with patch.dict(os.environ,{},clear=True),patch.object(sys,'argv',['server','--enable-model','--credential-file',str(self.key)]),patch.object(server,'Application',return_value=app)as factory,patch.object(server,'ThreadingHTTPServer',return_value=http),contextlib.redirect_stdout(io.StringIO()):
   server.main()
  self.assertEqual(factory.call_args.args[-2:],('gpt-6-sol','medium'))
  app.gateway.set_credential.assert_called_once_with(CANARY)
  app.gateway.request.assert_not_called();http.server_close.assert_called_once()
 def test_only_product_process_reads_validated_canary_into_memory(self):
  self.assertEqual(c.read_owner_credential(self.key),CANARY)
 def test_symlink_file_or_parent_is_rejected(self):
  link=self.private/'link';link.symlink_to(self.key)
  parent=Path(self.tmp.name)/'parent-link';parent.symlink_to(self.private,target_is_directory=True)
  for path in [link,parent/self.key.name]:
   with self.subTest(path=path),self.assertRaises(ValueError):c.read_owner_credential(path)
 def test_opened_descriptor_rejects_symlink_after_metadata_stage(self):
  link=self.private/'link';link.symlink_to(self.key)
  with patch.object(c,'inspect_owner_credential',return_value=link),self.assertRaises(OSError):c.read_owner_credential(link)
 def test_unprotected_or_wrong_owner_metadata_rejected(self):
  self.key.chmod(0o644)
  with self.assertRaises(ValueError):c.inspect_owner_credential(self.key)
  self.key.chmod(0o600)
  with patch.object(c.os,'geteuid',return_value=os.geteuid()+1),self.assertRaises(ValueError):c.inspect_owner_credential(self.key)
 def test_environment_presence_refused_without_value_access_or_echo(self):
  class PresenceOnly(dict):
   def __getitem__(self,key):raise AssertionError('Environment value must not be read')
  with patch.object(c.os,'environ',PresenceOnly(EVIDA_COMPETITION_API_KEY=CANARY)),self.assertRaises(ValueError)as ctx:c.reject_credential_environment()
  self.assertNotIn(CANARY,str(ctx.exception))
 def test_normal_and_probe_launch_pass_path_only_in_clean_environment(self):
  for probe in [False,True]:
   capture=[];args=['launch','--enable-model','--key-file',str(self.key),'--model','gpt-6-sol','--effort','medium']+(['--probe-model']if probe else[])
   with patch.dict(os.environ,{'PATH':'/usr/bin','LANG':'C.UTF-8'},clear=True),patch.object(sys,'argv',args),patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',side_effect=AssertionError('Launcher must not read key bytes')),patch.object(launch.os,'chdir'),patch.object(launch.os,'execve',side_effect=lambda *x:capture.append(x)):
    launch.main()
   self.assertEqual(len(capture),1);_,command,env=capture[0]
   self.assertIn('evida.transport_probe'if probe else'evida.server',command)
   self.assertEqual(command[command.index('--credential-file')+1],str(self.key))
   self.assertEqual(command[command.index('--model')+1],'gpt-6-sol');self.assertEqual(command[command.index('--effort')+1],'medium')
   self.assertFalse(set(c.FORBIDDEN_ENVIRONMENT)&set(env));self.assertNotIn(CANARY,json.dumps([command,env]))
if __name__=='__main__':unittest.main(verbosity=2)
