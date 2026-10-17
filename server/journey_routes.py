"""Validated map archives and durable acknowledgements for reviewed native trips."""
import hashlib
import json
import math
import tracking as t


def archive(value):
    if value is None:
        return None
    count = 0
    def fail(): t.fail('Invalid journey route. Keep the local copy and check the recorded route.')
    def number(v, minimum, maximum):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not minimum <= v <= maximum: fail()
        return v
    def point(p):
        nonlocal count
        if not isinstance(p, dict) or set(p) != {'latitude', 'longitude'}: fail()
        count += 1
        if count > 100000: t.fail('This route has too many points to upload. The local trip has been kept.')
        return dict(latitude=number(p['latitude'], -90, 90), longitude=number(p['longitude'], -180, 180))
    def points(values):
        if not isinstance(values, list) or not values: fail()
        return [point(p) for p in values]
    def text(v, limit=200):
        if not isinstance(v, str) or len(v) > limit or any(ord(c) < 32 for c in v): fail()
        return v
    def place(p):
        if not isinstance(p, dict) or set(p) != {'name', 'address', 'point'}: fail()
        return dict(name=text(p['name']), address=text(p['address']), point=point(p['point']))
    if not isinstance(value, dict) or set(value)-{'version','recorded','planned','start','finish','interrupted'} or value.get('version') != 1 or isinstance(value.get('version'),bool): fail()
    if not isinstance(value.get('recorded'),list) or len(value['recorded']) > 1000 or not isinstance(value.get('planned'),list) or len(value['planned']) > 1000 or not isinstance(value.get('interrupted'),bool): fail()
    result=dict(version=1, recorded=[points(segment) for segment in value['recorded']], planned=[], interrupted=value['interrupted'])
    for name in ['start','finish']:
        if value.get(name) is not None: result[name]=point(value[name])
    for route in value['planned']:
        if not isinstance(route,dict) or set(route)-{'id','name','from','to','via','points','metres','seconds'}: fail()
        try:
            result['planned'].append(dict(id=text(route['id'],36), name=text(route['name']), **{'from':place(route['from']),'to':place(route['to'])},
                                          points=points(route['points']), metres=number(route['metres'],1,100000000), seconds=number(route['seconds'],0,2592000)))
            if route.get('via') is not None: result['planned'][-1]['via']=place(route['via'])
        except KeyError: fail()
    encoded=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(encoded.encode('utf-8')) > 8*1024*1024: t.fail('This route is too large to upload. The local trip has been kept.')
    return encoded


def fingerprint(values, metadata, route):
    # Route JSON is canonical, and all journey fields have already been validated.
    return hashlib.sha256(json.dumps([values,metadata,route],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def acknowledgement(jid, ref, route):
    return dict(id=jid, client_ref=ref, route_saved=route is not None)
