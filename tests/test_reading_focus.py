"""Question focus must retain newly found opposing evidence and be reversible."""
import hashlib
import json
import unittest
from pathlib import Path
import tempfile

from evida.model_context import reading_focus, working_readings
from evida.runner import Runner
from evida.store import Store, dump


def view(rid, source, result, job='current'):
    content=json.dumps({'artifact_id':source,'result':result}).encode()
    return {'id':rid,'kind':'tool_reading','sha256':hashlib.sha256(content).hexdigest(),
            'meta':{'job_id':job,'function':'inspect_artifact',
                    'source_artifact_id':source,'arguments':{'artifact_id':source}},'content':content}


class ReadingFocusTests(unittest.TestCase):
    def test_new_opposition_and_conditions_survive_an_earlier_focus(self):
        rows=[view('old-large','unrelated',{'rows':['historical']*50}),
              view('positive','A',{'value':'y','condition':'C1'}),
              view('opposing','B',{'value':'no','condition':'unknown'}),
              view('conditions','C',{'value':None,'condition':'C2'})]
        lookup={r['id']:r for r in rows}
        hashes={r['id']:r['sha256'] for r in rows}
        focus={'reading_ids':['positive'],'existing_reading_ids':['old-large','positive']}
        kept=working_readings(rows,['current'],[],lookup.__getitem__,focus)
        self.assertEqual([r['reading_id'] for r in kept],['positive','opposing','conditions'])
        self.assertEqual(kept[1]['content']['result']['value'],'no')
        self.assertIsNone(kept[2]['content']['result']['value'])
        self.assertEqual(hashes,{r['id']:r['sha256'] for r in rows})
        self.assertEqual(len(json.loads(lookup['old-large']['content'])['result']['rows']),50)
        # Removing the focus restores the original cumulative view policy.
        self.assertEqual(len(working_readings(rows,'current',[],lookup.__getitem__)),4)

    def test_explicit_prior_view_can_be_reread_without_replaying_its_job(self):
        rows=[view('prior-condition','A',{'condition':'C1'},job='older'),
              view('current-opposition','B',{'value':'no'})]
        lookup={r['id']:r for r in rows}
        focus={'reading_ids':['prior-condition'],'existing_reading_ids':['prior-condition']}
        kept=working_readings(rows,'current',['current-opposition'],lookup.__getitem__,focus)
        self.assertEqual([r['reading_id'] for r in kept],['prior-condition'])
        self.assertEqual(kept[0]['meta']['job_id'],'older')

    def test_question_revision_and_new_frame_invalidate_old_focus_but_resume_keeps_it(self):
        frame={'kind':'work_framed','body':{'based_rev':3,'current_question':'synthetic Q1'}}
        focus={'kind':'reading_focus_set','body':{'based_rev':3,'job_id':'original',
                'current_question':'synthetic Q1','reading_ids':[],'existing_reading_ids':[]}}
        events=[frame,focus]
        self.assertIsNone(reading_focus(events,4,['original']))
        self.assertIsNone(reading_focus(events,3,['other']))
        self.assertEqual(reading_focus(events,3,['resumed','original']),focus['body'])
        events.append({'kind':'work_framed','body':{'based_rev':3,'current_question':'synthetic Q2'}})
        self.assertIsNone(reading_focus(events,3,['original']))


class ReadingFocusStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'synthetic.sqlite3')
        self.wid=self.store.create('Synthetic focus test')['id']
        self.jid=self.store.enqueue(self.wid,1,'planner',{})
        self.runner=object.__new__(Runner)
        self.runner.root=Path(__file__).resolve().parents[1]
        self.runner.store=self.store
        self.runner.frame(self.wid,1,{'current_question':'synthetic Q',
            'intent_records':[],'task_brief':[],'questions':[],'hypotheses':[]})
        self.source=self.store.add_artifact(self.wid,'Synthetic original','repository_document',
            dump({'rows':[{'value':'y'}],'limits':['synthetic']} ).encode(),{},bump=False)
        self.first=self.add_reading(self.source,'y')

    def tearDown(self):
        self.temp.cleanup()

    def add_reading(self,source,value):
        return self.store.add_artifact(self.wid,'Synthetic original view','tool_reading',
            dump({'artifact_id':source,'result':{'rows':[{'value':value}]}}).encode(),
            {'job_id':self.jid,'function':'inspect_artifact','source_artifact_id':source,
             'arguments':{'artifact_id':source}},bump=False)

    def test_runner_context_retains_new_opposing_view_and_all_original_records(self):
        before=self.store.artifact(self.wid,self.first)['sha256']
        self.runner.focus_readings(self.wid,1,self.jid,{'reading_ids':[self.first]})
        other=self.store.add_artifact(self.wid,'Synthetic contrary original','repository_document',
            dump({'rows':[{'value':'no'}],'limits':['synthetic']}).encode(),{},bump=False)
        opposite=self.add_reading(other,'no')
        context=self.runner.model_context(self.wid,1,True,current_job=self.jid)
        self.assertEqual({r['reading_id'] for r in context['WORKING_READINGS']},{self.first,opposite})
        self.assertEqual(context['READING_FOCUS']['current_question'],'synthetic Q')
        self.assertEqual(before,self.store.artifact(self.wid,self.first)['sha256'])
        self.assertIn(opposite,{v['reading_id'] for v in context['COMPLETED_VIEWS']})

    def test_raw_source_unframed_revision_or_duplicate_cannot_set_focus(self):
        count=len(self.store.snapshot(self.wid)['events'])
        with self.assertRaises(ValueError):
            self.runner.focus_readings(self.wid,1,self.jid,{'reading_ids':[self.source]})
        with self.assertRaises(ValueError):
            self.runner.focus_readings(self.wid,2,self.jid,{'reading_ids':[self.first]})
        with self.assertRaises(ValueError):
            self.runner.focus_readings(self.wid,1,self.jid,{'reading_ids':[self.first,self.first]})
        self.assertEqual(count,len(self.store.snapshot(self.wid)['events']))


if __name__=='__main__':
    unittest.main()
