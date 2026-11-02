"""312-only adapters and recorder, literal None deadlines; no global engine patch."""
from pathlib import Path
from contextvars import ContextVar
import hashlib,json
_SELECTED=ContextVar('native312_indexed_prompt',default=None)

def install_private_adapters(upstream):
 import codex356,recording356
 import lavi_research_os.providers.recording as original_recording
 pins=json.loads(Path(__file__).with_name('ENGINE_DERIVATIVE_PINS.json').read_text())
 for path,digest in pins['source_files'].items():
  if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('PINNED_ORIGINAL_ENGINE_CHANGED')
 # Original provider_workspace/observer ownership context is shared; not its timeout implementation.
 recording356._DIRECTORY=original_recording._DIRECTORY
 indexer=upstream._indexer
 original_prompt=codex356.task_prompt
 def render(task,payload):
  selected=_SELECTED.get()
  if selected is None:return original_prompt(task,payload)
  expected_task,expected_payload,prompt=selected
  if indexer.digest(task)!=expected_task or indexer.digest(payload)!=expected_payload:raise ValueError('INDEXED_INPUT_IDENTITY_CHANGED')
  return prompt
 codex356.task_prompt=render
 class NativeIndexedInputCodexAdapter(codex356.CodexSubscriptionAdapter):
  def __init__(self,source,packet_directory):
   super().__init__(binary=source.binary,model=source.model,reasoning_effort=source.reasoning_effort,timeout_seconds=None,allow_web_search=source.allow_web_search)
   self.packet_directory=Path(packet_directory);self.packet,self.prompt=indexer.verify_input_packet(self.packet_directory)
   if self.packet.get('format')!=indexer.FORMAT:raise ValueError('INDEXED_FORMAT_REQUIRED')
   self.read_root=Path(self.packet['read_root'])
  def build_command(self,workspace,schema_path,output_path):return super().build_command(self.read_root,schema_path,output_path)
  def contract_identity(self):
   value=dict(super().contract_identity());value.update(input_packet_sha256=indexer.digest(self.packet),working_directory=str(self.read_root),input_access_policy=self.packet['reading_policy']);return value
  def complete_json(self,*,task,payload,schema,workspace):
   packet,prompt=indexer.verify_input_packet(self.packet_directory)
   if indexer.digest(task)!=packet['original_task_sha256']or indexer.digest(payload)!=packet['original_payload_sha256']or Path(workspace).resolve().is_relative_to(self.read_root):raise ValueError('INDEXED_CONTEXT_OR_SCOPE_CHANGED')
   token=_SELECTED.set((indexer.digest(task),indexer.digest(payload),prompt))
   try:return super().complete_json(task=task,payload=payload,schema=schema,workspace=workspace)
   finally:_SELECTED.reset(token)
 upstream.CodexSubscriptionAdapter=codex356.CodexSubscriptionAdapter
 upstream.IndexedInputCodexAdapter=NativeIndexedInputCodexAdapter
 return NativeIndexedInputCodexAdapter
