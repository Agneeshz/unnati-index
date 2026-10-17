// Builds web/src/geo/cities.topo.json: the municipal boundary of each city on the roster, for the
// zoomed-in maps. No official open dataset of Indian municipal boundaries exists, so they come
// from OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0; this file is ODbL too).
//
// For each city, in order:
// 1. COMBINED: cities whose corporation is a union of OSM areas (Mumbai = two districts);
// 2. the administrative boundary tagged with the city's Wikidata item;
// 3. a municipal-level boundary (admin_level 6-9) containing the city's point whose name matches
//    the city's, the most local level first.
// A boundary is used only if it holds (or comes within 2 km of) the city's point and covers
// 5-1,600 km²; other cities
// stay a dot. Overpass is queried in two batches (candidates, then shapes), cached in
// geo/build/osm/; delete the cache to refresh. The build prints how each city was matched.
import { existsSync } from 'node:fs'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { geoArea, geoContains, geoDistance } from 'd3-geo'
import mapshaper from 'mapshaper'
import osmtogeojson from 'osmtogeojson'

const here = import.meta.dirname
const cache = path.join(here, 'build', 'osm')
const output = path.join(here, '..', 'web', 'src', 'geo', 'cities.topo.json')
const citiesCsv = path.join(here, '..', 'pipeline', 'src', 'unnati', 'reference', 'cities.csv')
const SERVERS = ['https://overpass-api.de/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter']
const USER_AGENT = 'unnati-index map build (+https://github.com/Agneeshz/unnati-index)'
const KM2_PER_STERADIAN = 6371 ** 2
const MIN_KM2 = 5
const MAX_KM2 = 1600 // Delhi's corporations cover about 1,400 km²
// Corporations made of several OSM areas: Brihanmumbai Municipal Corporation covers Mumbai City
// and Mumbai Suburban districts exactly.
const COMBINED = { mumbai: [7964376, 7964375] }
// Cities whose Wikidata-tagged OSM area is something larger (the whole district).
const SKIP = new Set(['puducherry-city'])
// A city's listed point may sit just outside its corporation (Howrah, Mysuru): within 2 km is fine.
const NEAR_KM = 2

const norm = (s) =>
  (s ?? '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z]+/g, ' ')
    .trim()
// Words that name the body rather than the place.
const BODY =
  /\b(municipal|corporation|city|nagar nigam|mahanagar palika|mahanagarapalike|greater|brihan|bruhat|council|municipality|cantonment|the|of)\b/g
const core = (s) => norm(s).replace(BODY, ' ').replace(/\s+/g, ' ').trim()

async function overpass(name, query) {
  const file = path.join(cache, `${name}.json`)
  if (existsSync(file)) return JSON.parse(await readFile(file, 'utf8'))
  for (let attempt = 0; attempt < 8; attempt++) {
    const server = SERVERS[attempt % SERVERS.length]
    try {
      const response = await fetch(server, {
        method: 'POST',
        headers: { 'User-Agent': USER_AGENT, 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ data: query }),
        signal: AbortSignal.timeout(900_000),
      })
      const text = await response.text()
      if (response.ok && text.startsWith('{')) {
        await mkdir(cache, { recursive: true })
        await writeFile(file, text)
        return JSON.parse(text)
      }
      console.log(`${name}: ${server} answered ${response.status}, retrying`)
    } catch (err) {
      console.log(`${name}: ${server} ${err.name}, retrying`)
    }
    await new Promise((r) => setTimeout(r, 30_000 * (attempt + 1)))
  }
  throw new Error(`Overpass unavailable for ${name}`)
}

/** Distance from a point to the nearest vertex of a geometry, in km (vertices are dense enough). */
function nearestKm(geometry, point) {
  let best = Infinity
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
  for (const polygon of polygons) for (const ring of polygon) for (const v of ring) best = Math.min(best, geoDistance(point, v))
  return best * 6371
}

function reversed(geometry) {
  const flip = (polygon) => polygon.map((ring) => [...ring].reverse())
  return geometry.type === 'Polygon'
    ? { type: 'Polygon', coordinates: flip(geometry.coordinates) }
    : { type: 'MultiPolygon', coordinates: geometry.coordinates.map(flip) }
}

const [header, ...lines] = (await readFile(citiesCsv, 'utf8')).trim().split(/\r?\n/)
const cols = header.split(',')
const cities = lines.map((line) => Object.fromEntries(line.split(',').map((v, i) => [cols[i], v])))

// 1. Candidates for every city in one query: a marker element per city, then the boundaries
//    around its point, then any boundary carrying its Wikidata item.
const parts = cities.map(
  (c) =>
    `make city slug="${c.slug}";out;is_in(${c.latitude},${c.longitude})->.a;` +
    `(relation(pivot.a)["boundary"="administrative"]["admin_level"~"^[6-9]$"];relation(pivot.a)["boundary"="local_authority"];);out tags;` +
    `relation["wikidata"="${c.wikidata_qid}"]["boundary"];out tags;`,
)
const listing = await overpass('city-candidates', `[out:json][timeout:900];${parts.join('')}`)
const candidates = new Map()
let current = null
for (const e of listing.elements) {
  if (e.type === 'city') current = e.tags.slug
  else if (current) candidates.get(current)?.push(e) ?? candidates.set(current, [e])
}

const choices = new Map()
for (const city of cities) {
  if (SKIP.has(city.slug)) {
    choices.set(city.slug, [])
    continue
  }
  if (COMBINED[city.slug]) {
    choices.set(city.slug, [{ ids: COMBINED[city.slug], how: 'combined areas' }])
    continue
  }
  const names = [city.name, city.cpcb_name, city.ncrb_name].filter(Boolean).map(core)
  const seen = new Set()
  const ranked = (candidates.get(city.slug) ?? [])
    .filter((e) => !seen.has(e.id) && seen.add(e.id))
    .map((e) => {
      const t = e.tags
      const label = [t.name, t['name:en'], t.official_name, t.alt_name].filter(Boolean)
      // Level 6 is usually a tehsil or taluk named after its town, larger than the city: only
      // taken when the name says it is the municipal body.
      const municipal = /municipal|corporation|nagar nigam|palika|palike/i.test(label.join(' '))
      const tehsil = t.admin_level === '6' && !municipal
      const how =
        t.wikidata === city.wikidata_qid
          ? 'wikidata'
          : !tehsil && label.some((l) => names.includes(core(l)))
            ? `name "${t.name}" (${t.boundary === 'local_authority' ? 'local authority' : `level ${t.admin_level}`})`
            : null
      return { ids: [e.id], how, level: Number(t.admin_level ?? 0) }
    })
    .filter((c) => c.how)
    // Wikidata first, then the most local level (8 is the municipal corporation in most states).
    .sort((a, b) => Number(b.how === 'wikidata') - Number(a.how === 'wikidata') || b.level - a.level)
  choices.set(city.slug, ranked)
}

// 2. Every candidate shape in one query.
const ids = [...new Set([...choices.values()].flat().flatMap((c) => c.ids))]
const shapesById = new Map()
if (ids.length) {
  const geo = osmtogeojson(await overpass('city-shapes', `[out:json][timeout:900];relation(id:${ids.join(',')});out geom;`))
  for (const f of geo.features) {
    const id = Number(String(f.id).replace('relation/', ''))
    if (f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon') shapesById.set(id, f.geometry)
  }
}

// 3. The first candidate that holds the city's point and has a plausible size.
const features = []
for (const [i, city] of cities.entries()) {
  let how = 'no matching boundary'
  for (const choice of choices.get(city.slug) ?? []) {
    const geometries = choice.ids.map((id) => shapesById.get(id))
    if (geometries.some((g) => !g)) continue
    const polygons = geometries.flatMap((g) => (g.type === 'Polygon' ? [g.coordinates] : g.coordinates))
    const geometry = { type: 'MultiPolygon', coordinates: polygons }
    // osmtogeojson winds rings the GeoJSON way; d3 reads that as the rest of the globe, so the
    // checks use a reversed copy (mapshaper accepts either).
    const forD3 = { type: 'Feature', geometry: reversed(geometry) }
    const km2 = geoArea(forD3) * KM2_PER_STERADIAN
    const point = [Number(city.longitude), Number(city.latitude)]
    const holds = geoContains(forD3, point) || nearestKm(geometry, point) <= NEAR_KM
    if (!holds || km2 < MIN_KM2 || km2 > MAX_KM2) {
      how = `rejected ${choice.how}: ${holds ? '' : 'point outside, '}${Math.round(km2)} km²`
      continue
    }
    how = `${choice.how}, ${Math.round(km2)} km²`
    features.push({ type: 'Feature', properties: { slug: city.slug }, geometry })
    break
  }
  console.log(`${String(i + 1).padStart(3)} ${city.slug.padEnd(28)} ${how}`)
}
console.log(`${features.length} of ${cities.length} cities have a boundary`)

const result = await mapshaper.applyCommands(
  [
    '-i cities.json name=cities',
    '-dissolve2 slug',
    '-simplify interval=30 keep-shapes',
    '-o cities.topo.json format=topojson quantization=1000000',
  ].join(' '),
  { 'cities.json': JSON.stringify({ type: 'FeatureCollection', features }) },
)
await writeFile(output, result['cities.topo.json'])
console.log(`wrote ${path.relative(process.cwd(), output)} (${Math.round(result['cities.topo.json'].length / 1024)} KB)`)
