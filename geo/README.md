# Map boundaries

Two files are generated from the same source by `npm run geo:build` (`geo/build.mjs`) and
committed, so the site build does not depend on a download:

- `web/public/geo/india-states.topo.json` (2% of the source's points, about 140 KB): national
  and state-sized maps.
- `web/src/geo/india-states-detailed.topo.json` (20%, about 1 MB): zoomed-in maps (city
  close-ups, crowded-area insets, the smallest states). It is used on the server only, and maps
  clip it to their frame, so a page carries only the detail of the area it shows.

## Source and licence

- **Data:** [DataMeet `States/Admin2`](https://github.com/datameet/maps/tree/master/States),
  pinned to commit `2c0c306a`. That commit's history aligns the Jammu & Kashmir and Ladakh
  boundaries with the latest Survey of India map and reflects the January 2020 status
  (Dadra and Nagar Haveli and Daman and Diu merged).
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Attribution:
  *India state boundaries by [DataMeet India community](http://datameet.org/) (CC BY 4.0)*.

## Rules

- The external boundary of India must follow the official Survey of India map. The site never
  uses a tile basemap (OpenStreetMap or commercial tiles show disputed areas differently).
- Every map shows the note "Boundaries as per Survey of India; not an authenticated map."
- Each shape carries our entity `slug`, so data joins never depend on spelling.

## Processing

`-clean` (repairs topology) → `-simplify 2% weighted keep-shapes` (keeps every small UT and island
group) → TopoJSON with shared borders, quantised; the detailed file uses `-simplify 20%`. Run `-clean` before
`-simplify`: run after it, it rebuilds the full-detail geometry (4.7 MB).

Small UTs (Chandigarh, Delhi, Puducherry, Lakshadweep, DNH & DD) are hard to see at national
scale, so map components must add labelled markers for them and always offer a table view.

## Water on zoomed-in maps

The state boundaries count inland water (harbours, creeks, backwaters, lakes, wide rivers) as
land, which makes city close-ups misleading: Mumbai and Navi Mumbai look like one landmass and
Kochi has no backwaters. `node geo/water.mjs` builds `web/src/geo/water.topo.json` (server-only),
which close-ups and insets (more than 8x the national scale) draw over the states:

- **Sea:** [osmdata.openstreetmap.de water polygons](https://osmdata.openstreetmap.de/data/water-polygons.html)
  (`water-polygons-split-4326.zip`, about 900 MB), unzipped into `geo/build/osm/`.
- **Inland water:** [Geofabrik's India extracts](https://download.geofabrik.de/asia/india.html),
  six zones (`<zone>-latest-free.shp.zip`, about 4 GB together); only the
  `gis_osm_water_a_free_1.*` layer is kept, renamed `geo/build/osm/geofabrik/<zone>-water.*`.
  Classes water, reservoir, river, riverbank and dock, 0.25 km² or larger.
- Only boxes of ±0.75° longitude by ±0.5° latitude around each city are kept, merged and
  simplified to about 30 m.
- **Licence:** © OpenStreetMap contributors, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/);
  `water.topo.json` is a derived database under the same licence. Maps that show water carry the
  credit "Water © OpenStreetMap contributors (ODbL)".

India's external boundary still comes from the state boundaries (Survey of India); water only
changes how inland water looks near cities. Rebuild after adding cities to the roster.
