"""Bounded process fixtures, not scientific computations."""
import hashlib,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from evida import pocket_docking as p
class RuntimeTests(unittest.TestCase):
 def test_timeout_kills_descendant_pipe_even_after_parent_exit(self):
  actual=subprocess.Popen
  fixture="import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); sys.exit(0)"
  def spawn(argv,**kw):return actual([sys.executable,'-c',fixture],**kw)
  with tempfile.TemporaryDirectory()as t,patch.object(p,'TIMEOUT_SECONDS',.2),patch.object(p.subprocess,'Popen',side_effect=spawn):
   start=time.monotonic();r=p.run(b'x',{}, {'geometry':{'pocket_id':1}},Path(t)/'work');self.assertLess(time.monotonic()-start,3);self.assertEqual(r['error'],'timeout');self.assertEqual(r['status'],'failed')
 def test_oversize_failure_stream_hashes_actual_bytes(self):
  actual=subprocess.Popen
  fixture="from pathlib import Path; import os; p=Path('large.part'); p.write_bytes(b'x'*1048576); os.replace(p,'large.bin')"
  def spawn(argv,**kw):return actual([sys.executable,'-c',fixture],**kw)
  read_bytes=Path.read_bytes
  def guarded(path):
   if path.name=='large.bin':raise AssertionError('oversized file must not be loaded with read_bytes')
   return read_bytes(path)
  with tempfile.TemporaryDirectory()as t,patch.object(p,'OUTPUT_LIMIT_BYTES',131072),patch.object(p.subprocess,'Popen',side_effect=spawn),patch.object(Path,'read_bytes',guarded):
   r=p.run(b'x',{}, {'geometry':{'pocket_id':1}},Path(t)/'work');self.assertEqual(r['error'],'output_limit');entry=next(x for x in r['retained_files']if x['name']in('large.bin','large.part'));self.assertGreater(entry['bytes'],131072);self.assertEqual(len(entry['sha256']),64)
 def test_cancel_marker_is_explicit_and_bounded(self):
  actual=subprocess.Popen;folder=None
  def spawn(argv,**kw):
   Path(kw['cwd'],'cancel').write_text('software fixture');return actual([sys.executable,'-c','import time;time.sleep(30)'],**kw)
  with tempfile.TemporaryDirectory()as t,patch.object(p.subprocess,'Popen',side_effect=spawn):
   r=p.run(b'x',{}, {'geometry':{'pocket_id':1}},Path(t)/'work');self.assertEqual(r['error'],'cancelled');self.assertEqual(r['status'],'failed')
if __name__=='__main__':unittest.main()
