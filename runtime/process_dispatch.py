"""Linux cross-process admission: persistent numbering/cap and OS-owned slots.
No provider invocation. Crash releases flock slots; preserved call directories still count.
Legacy max processes must be stopped before this explicit profile transition.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import fcntl,json,time,os
class DispatchPaused(RuntimeError):pass
@dataclass(frozen=True)
class Admission:
 index:int
 root:Path
 queue_seconds:float
class BoundedDispatch:
 def __init__(self,root,maximum=2,hold_path=None):
  if maximum != 2:raise ValueError('Shared concurrency must be exactly two')
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.maximum=maximum
  self.hold_path=Path(hold_path) if hold_path else self.root/'dispatch-hold-high.json'
 def _indices(self):return [int(p.name[5:]) for p in self.root.glob('call-*') if p.is_dir() and p.name[5:].isdigit()]
 @property
 def next_index(self):return max(self._indices(),default=0)+1
 def pause(self,reason):
  try:
   with self.hold_path.open('x') as f:json.dump({'reason':str(reason),'automatic_resume':False},f)
  except FileExistsError:pass
 def check_dispatch(self):
  if self.hold_path.exists():raise DispatchPaused('Preserved high-profile dispatch hold')
 def snapshot(self):
  active=0
  for i in range(2):
   with (self.root/f'.subscription-slot-{i}.lock').open('a+') as f:
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:active+=1
    else:fcntl.flock(f,fcntl.LOCK_UN)
  return {'maximum':2,'active':active,'queued':None,'paused':self.hold_path.exists(),'count_basis':'persistent call directories; queued count unavailable across processes'}
 @contextmanager
 def admit(self):
  started=time.monotonic();slot=None
  try:
   while slot is None:
    self.check_dispatch()
    for i in range(2):
     f=(self.root/f'.subscription-slot-{i}.lock').open('a+')
     try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:f.close()
     else:slot=f;break
    if slot is None:time.sleep(.02)
   with (self.root/'.subscription-admission.lock').open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);self.check_dispatch();index=self.next_index
    if index>60:raise DispatchPaused('Shared stage cap 60 reached before new admission')
    root=self.root/f'call-{index:04d}';root.mkdir(mode=0o700,exist_ok=False)
    (root/'admission.json').write_text(json.dumps({'index':index,'pid':os.getpid(),'at':time.time(),'shared_stage_cap':60,'concurrency_limit':2})+'\n')
    fcntl.flock(lock,fcntl.LOCK_UN)
   yield Admission(index,root,time.monotonic()-started)
  finally:
   if slot is not None:fcntl.flock(slot,fcntl.LOCK_UN);slot.close()
