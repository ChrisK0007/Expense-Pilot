"""Offline Australian suburb lookup. Unknown or ambiguous evidence stays unknown."""
import json
import gzip
import math
import re
import statistics
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


def norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text or '').casefold()).strip()


@lru_cache(maxsize=1)
def catalogue():
    entries = {}; names = defaultdict(list); areas = defaultdict(list)
    raw = []
    for path in sorted((Path(__file__).parent/'datasets'/'au-suburbs').glob('*.json.gz')):
        raw.extend(json.loads(gzip.decompress(path.read_bytes())))
    for code, name, state, postcode, lat, lon, urban, area in raw:
        key = 'suburb:'+code
        item = dict(id=key, name=name, state=state, postcode=postcode, latitude=lat, longitude=lon, kind='suburb')
        entries[key] = item; names[norm(name)].append(item)
        if area:
            areas[(area,state)].append(item)
    for (area,state), suburbs in areas.items():
        key = 'area:'+state+':'+norm(area)
        item = dict(id=key, name=area, state=state, postcode='', latitude=statistics.median(x['latitude'] for x in suburbs), longitude=statistics.median(x['longitude'] for x in suburbs), kind='area')
        entries[key] = item; names[norm(area)].append(item)
    return entries, names


def label(item):
    return f"{item['name']}, {item['state']}" + (f" {item['postcode']}" if item['postcode'] else ' (area centre)')


def get_place(key):
    return catalogue()[0].get(key)


def hints(text):
    upper = str(text).upper()
    state = re.findall(r'\b(ACT|NSW|NT|QLD|SA|TAS|VIC|WA)\b',upper)
    replacements = {'QUEENSLAND':'QLD','NEW SOUTH WALES':'NSW','VICTORIA':'VIC','TASMANIA':'TAS','SOUTH AUSTRALIA':'SA','WESTERN AUSTRALIA':'WA','NORTHERN TERRITORY':'NT','AUSTRALIAN CAPITAL TERRITORY':'ACT'}
    state += [v for k,v in replacements.items() if k in upper]
    # A bare street number is not evidence of a postcode.
    postcodes = re.findall(r'\b(?:ACT|NSW|NT|QLD|SA|TAS|VIC|WA)\s+(\d{4})\b',upper)
    return set(state), set(postcodes)


def unique(candidates):
    # An area and identically named suburb in the same state represent one place;
    # prefer the suburb's point. Different states or postcodes remain ambiguous.
    localities = [x for x in candidates if x['kind']=='suburb']
    candidates = localities or candidates
    identities = {(x['state'],x['postcode'],norm(x['name'])):x for x in candidates}
    return next(iter(identities.values())) if len(identities)==1 else None


def resolve(name, address=''):
    entries,names = catalogue(); state,postcodes=hints(str(name)+' '+str(address))
    def narrow(candidates):
        return [x for x in candidates if (not state or x['state'] in state) and (not postcodes or x['postcode'] in postcodes or x['kind']=='area')]
    words = norm(name).split()
    words = [w for w in words if w.upper() not in state and w not in postcodes and w not in ('australia','au')]
    exact = narrow(names.get(' '.join(words),[]))
    # First find a precise suburb in the receipt address, prioritising longest names.
    words = norm(address).split()
    matches=[]; longest=0
    for length in range(min(6,len(words)),0,-1):
        for start in range(len(words)-length+1):
            found=narrow(names.get(' '.join(words[start:start+length]),[]))
            found=[x for x in found if x['kind']=='suburb']
            if found:
                matches.extend(found); longest=length
        if longest: break
    if matches:
        return unique(matches)
    return unique(exact)


def receipt_location(values):
    """A reviewed location overrides raw AI evidence without discarding it."""
    if 'merchant_location' in values:
        return str(values['merchant_location'] or '').strip()
    city = str(values.get('merchant_city') or '').strip()
    address = values.get('merchant_address') or ''
    if values.get('currency') not in (None, '', 'AUD') and not hints(city+' '+address)[0]:
        return city
    place = resolve(city, address)
    if place:
        return f"{place['name']}, {place['state']}" + (f" {place['postcode']}" if place['postcode'] else '')
    states, _ = hints(address)
    if city and len(states) == 1 and not hints(city)[0]:
        return f"{city}, {next(iter(states))}"
    return city


def search(query):
    q=norm(query)
    if len(q)<2: return []
    words=q.split(); found=[]
    for item in catalogue()[0].values():
        text=norm(label(item))
        if all(word in text for word in words):
            found.append(item)
    found.sort(key=lambda x:(norm(x['name'])!=q,not norm(x['name']).startswith(q),x['kind']!='area',x['name'],x['state']))
    return [{**item,'label':label(item)} for item in found[:20]]


def distance_km(a,b):
    lat1,lat2=math.radians(a['latitude']),math.radians(b['latitude'])
    dlat=lat2-lat1; dlon=math.radians(b['longitude']-a['longitude'])
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371.0088*2*math.asin(min(1,math.sqrt(h)))


def home_place(prefs):
    return get_place(prefs.get('home_place_id')) or resolve(prefs.get('home_base',''))


def local_assessment(prefs, city, address='', currency='AUD'):
    aliases=[prefs.get('home_base',''),*prefs.get('home_aliases','').split(',')]
    states,postcodes=hints(str(city)+' '+str(address))
    home=home_place(prefs)
    # Explicit foreign-currency evidence needs review unless an AU state is supplied.
    if currency and currency!='AUD' and not states:
        return dict(status='unknown',reason='Check the receipt country and location.')
    place=resolve(city,address)
    if not home:
        if norm(city) and norm(city) in {norm(x) for x in aliases}:
            return dict(status='local',reason='Matches a saved local name.')
        return dict(status='unknown',reason='Select a recognised home base in receipt preferences.')
    if states and home['state'] not in states and norm(city) in {norm(x) for x in aliases}:
        pass  # Identical suburb names in different states must not match an alias.
    elif norm(city) and norm(city) in {norm(x) for x in aliases} and not (place and place['state']!=home['state']):
        return dict(status='local',reason='Matches a saved local name.')
    if not place:
        return dict(status='unknown',reason='Location is missing or ambiguous; review the receipt.')
    km=distance_km(home,place); radius=float(prefs.get('local_radius_km',50))
    return dict(status='local' if km<=radius else 'away',distance_km=round(km,1),location=label(place),reason=f"Approximately {km:.0f} km from home base; local radius {radius:g} km.")


def coverage(prefs):
    home=home_place(prefs)
    if not home:return dict(resolved=False,local_count=0,examples=[])
    radius=float(prefs.get('local_radius_km',50))
    local=sorted([(distance_km(home,x),x) for x in catalogue()[0].values() if x['kind']=='suburb'],key=lambda x:x[0])
    local=[x for km,x in local if km<=radius]
    return dict(resolved=True,place={**home,'label':label(home)},local_count=len(local),examples=[label(x) for x in local[:12]])
