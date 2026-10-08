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
