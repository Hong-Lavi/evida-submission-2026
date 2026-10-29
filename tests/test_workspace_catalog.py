from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from evida.store import Store
from evida.workspace_catalog import WorkspaceCatalog,catalog_handler

class WorkspaceCatalogTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();p=Path(self.temp.name)
        self.a,self.b=Store(p/'a.sqlite3'),Store(p/'b.sqlite3')
        self.wa,self.wb=self.a.create('Small molecule'),self.b.create('RNA')
        self.apps={'new':SimpleNamespace(store=self.a),'existing':SimpleNamespace(store=self.b)}
        self.catalog=WorkspaceCatalog(self.apps,'new')
    def tearDown(self): self.temp.cleanup()
    def test_same_event_ordinals_are_preserved_under_workspace_owner(self):
        self.assertEqual(self.wa['event_cursor'],self.wb['event_cursor'])
        self.assertEqual(self.catalog.owner(self.wa['id']),'new')
        self.assertEqual(self.catalog.owner(self.wb['id']),'existing')
        self.b.command(self.wb['id'],1,'rna-input',{'kind':'message','text':'RNA condition','synthetic':True})
        self.assertEqual(self.a.snapshot(self.wa['id']),self.wa)
        self.assertEqual(self.b.snapshot(self.wb['id'])['rev'],2)
        self.assertEqual(len(self.catalog.list()),2)
    def test_new_workspaces_are_found_without_a_stale_startup_map(self):
        w=self.a.create('New question');self.assertEqual(self.catalog.owner(w['id']),'new')
        with self.assertRaises(KeyError): self.catalog.owner('missing')
    def test_duplicate_identity_fails_closed_without_selecting_a_store(self):
        with self.b.connect(True) as db:
            db.execute('UPDATE workspaces SET id=? WHERE id=?',(self.wa['id'],self.wb['id']))
        with self.assertRaisesRegex(ValueError,'Duplicate workspace'): self.catalog.list()
        with self.assertRaisesRegex(ValueError,'Duplicate workspace'): WorkspaceCatalog(self.apps,'new')
    def test_each_request_routes_to_its_own_closure(self):
        received=[]
        threaded=[]
        def factory(app,public_hosts=()):
            # Recorded separately: `received` counts dispatches, and the host allowance is
            # passed once per store at construction rather than per request.
            threaded.append(tuple(public_hosts))
            class FakeHandler:
                def check_local(self): received.append(('local',self.path))
                def send(self,value,status=200): return status,value
                def dispatch(self,post): return app,post,self.path
            return FakeHandler
        with patch('evida.workspace_catalog.handler_for',factory): cls=catalog_handler(self.catalog)
        request=object.__new__(cls)
        request.path='/api/workspaces/'+self.wb['id']+'/commands'
        self.assertIs(request.dispatch(True)[0],self.apps['existing'])
        request.path='/api/workspaces/'+self.wa['id']+'/jobs'
        self.assertIs(request.dispatch(True)[0],self.apps['new'])
        request.path='/api/workspaces/'+self.wb['id']+'/artifacts/art_missing?offset=0'
        self.assertIs(request.dispatch(False)[0],self.apps['existing'])
        request.path='/api/workspaces';self.assertEqual(len(request.dispatch(False)[1]),2)
        self.assertIs(request.dispatch(True)[0],self.apps['new'])
        request.path='/api/workspaces/missing/commands';self.assertEqual(request.dispatch(True)[0],404)
        self.assertEqual(len(received),6)
        # Every store gets the same host allowance, so one of them cannot be reached under a
        # name the others refuse.
        self.assertEqual(len(threaded),len(self.apps))
        self.assertEqual(set(threaded),{()})
    def test_origin_validation_also_protects_catalog_listing(self):
        class Denied:
            def check_local(self): raise ValueError('denied origin')
            def send(self,value,status=200): return status,value
        with patch('evida.workspace_catalog.handler_for',return_value=Denied):
            request=object.__new__(catalog_handler(self.catalog));request.path='/api/workspaces'
            self.assertEqual(request.dispatch(False),(400,{'error':'denied origin'}))
