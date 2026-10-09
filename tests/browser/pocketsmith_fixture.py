"""PocketSmith fixture used only by the disposable browser-test server."""
from datetime import date
from pocketsmith_client import FeedError


class BrowserClient:
    def __init__(self, key):
        if key != 'browser-pocketsmith-test-key':
            raise FeedError('PocketSmith access was denied. Check your developer key.')
    def get(self, path):
        return {'id':71, 'name':'Browser bank feed'}, {}
    def collection(self, path, params=None):
        if 'users' in path:
            return [{'id':81, 'name':'PocketSmith browser account', 'currency_code':'AUD', 'institution':{'title':'Test bank'}}]
        return [
            {'id':91, 'payee':'PocketSmith browser purchase', 'amount':-36.75, 'date':date.today().isoformat(), 'status':'posted', 'is_transfer':None},
            {'id':92, 'payee':'PocketSmith browser pending', 'amount':-17, 'date':date.today().isoformat(), 'status':'pending', 'is_transfer':None},
            {'id':93, 'payee':'PocketSmith browser transfer', 'amount':-50, 'date':date.today().isoformat(), 'status':'posted', 'is_transfer':None, 'category':{'title':'Transfers','is_transfer':True}},
            {'id':94, 'payee':'PocketSmith browser matching receipt', 'amount':-82.19, 'date':date.today().isoformat(), 'status':'posted', 'is_transfer':False},
        ]
