# Australian suburb lookup

`au-suburbs/*.json.gz` contains compressed offline extracts from [michalsn/australian-suburbs](https://github.com/michalsn/australian-suburbs), CSV blob `846ca1f24043d923803d069a63d7c969bdf0d37a`, retrieved 8 October 2026. The upstream data is mainly based on the 2016 Census. See `LICENSE-au-suburbs.txt` for the MIT licence.

Each row contains suburb code, name, state, postcode, latitude, longitude, urban area and local government area. Invalid coordinates were excluded and council-type suffixes removed. This is an approximate locality-centre lookup, not an address validator or a tax definition of travel. Regional centres use the median of their suburb coordinates. New suburbs or ambiguous names may need a manual correction. No receipt location is sent to a geocoding service.
