"""One selector over preserved stores; no event renumbering or artifact rewriting."""
from urllib.parse import urlparse
from .server import handler_for

class WorkspaceCatalog:
    def __init__(self, apps, primary):
        self.apps=dict(apps)
        if not self.apps or primary not in self.apps:
            raise ValueError('A primary research store must be explicitly configured.')
        self.primary=primary
        self._index()

    def _index(self):
        owners={};rows=[]
        for name,app in self.apps.items():
            for row in app.store.list():
                wid=row['id']
                if wid in owners:
                    raise ValueError('Duplicate workspace identity across stores; explicit resolution is required.')
                owners[wid]=name;rows.append(row)
        return owners,sorted(rows,key=lambda r:(r['created'],r['id']),reverse=True)

    def list(self):
        return self._index()[1]

    def owner(self,wid):
        owners,_=self._index()
        if wid not in owners: raise KeyError('워크스페이스를 찾지 못했습니다.')
        return owners[wid]


def catalog_handler(catalog, public_hosts=()):
    handlers={name:handler_for(app,public_hosts) for name,app in catalog.apps.items()}
    primary=handlers[catalog.primary]
    class Handler(primary):
        def dispatch(self,post):
            try:
                self.check_local()
                route=urlparse(self.path).path.strip('/').split('/')
                if route==['api','workspaces'] and not post:
                    return self.send(catalog.list())
                owner=catalog.primary
                if len(route)>=3 and route[:2]==['api','workspaces']:
                    owner=catalog.owner(route[2])
                # Each handler closes over one app; no global current-app mutation.
                return handlers[owner].dispatch(self,post)
            except KeyError:
                return self.send({'error':'워크스페이스를 찾지 못했습니다.'},404)
            except ValueError as exc:
                return self.send({'error':str(exc)},400)
    return Handler
