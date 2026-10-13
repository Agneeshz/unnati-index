// Builds web/src/geo/water.topo.json: sea and large inland water (harbours, creeks, backwaters,
// lakes, wide rivers) around every city, for the zoomed-in maps. The official state boundaries
// count inland water as land, so close-ups draw this water over them.
//
// Source: OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0), so this file is ODbL too.
// - Sea: osmdata.openstreetmap.de water polygons (WGS84, split into 1° tiles).
// - Inland water: Geofabrik's India extracts (six zones), layer gis_osm_water_a_free_1.
// Both are large downloads kept out of git in geo/build/osm/ (see geo/README.md). Only areas
// around cities are kept (close-ups and insets never leave them); India's external boundary is
// untouched (it comes from the state boundaries, as per Survey of India).
import { existsSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { geoArea } from 'd3-geo'
import mapshaper from 'mapshaper'
import * as shapefile from 'shapefile'

const here = import.meta.dirname
const cache = path.join(here, 'build', 'osm')
const SEA = path.join(cache, 'water-polygons-split-4326', 'water_polygons')
const ZONES = ['central-zone', 'eastern-zone', 'north-eastern-zone', 'northern-zone', 'southern-zone', 'western-zone']
const output = path.join(here, '..', 'web', 'src', 'geo', 'water.topo.json')
const citiesCsv = path.join(here, '..', 'pipeline', 'src', 'unnati', 'reference', 'cities.csv')

// Coverage around each city: close-ups span ±45 km in a 4:3 frame, insets less.
const HALF_LON = 0.75
const HALF_LAT = 0.5
// Smaller water bodies are dropped (ponds and tanks would be specks at close-up scale).
const MIN_AREA_KM2 = 0.25
const EARTH_KM2 = 4 * Math.PI * 6371 ** 2
// Geofabrik water classes drawn (wetland and glacier are not open water).
const INLAND = new Set(['water', 'reservoir', 'river', 'riverbank', 'dock'])

async function cityBoxes() {
  const [header, ...lines] = (await readFile(citiesCsv, 'utf8')).trim().split(/\r?\n/)
  const cols = header.split(',')
  return lines.map((line) => {
    const c = Object.fromEntries(line.split(',').map((v, i) => [cols[i], v]))
    const lon = Number(c.longitude)
    const lat = Number(c.latitude)
    return [lon - HALF_LON, lat - HALF_LAT, lon + HALF_LON, lat + HALF_LAT]
  })
}

const intersects = (a, b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]

function bbox(geometry) {
  const box = [Infinity, Infinity, -Infinity, -Infinity]
  const visit = (c) => {
    if (typeof c[0] === 'number') {
      box[0] = Math.min(box[0], c[0])
      box[1] = Math.min(box[1], c[1])
      box[2] = Math.max(box[2], c[0])
      box[3] = Math.max(box[3], c[1])
    } else c.forEach(visit)
  }
  visit(geometry.coordinates)
  return box
}

/** Polygons from a shapefile that reach into any city box (and pass `keep`). */
async function near(file, boxes, keep = () => true) {
  if (!existsSync(`${file}.shp`)) throw new Error(`missing ${file}.shp: see geo/README.md for the downloads`)
  const source = await shapefile.open(`${file}.shp`, `${file}.dbf`, { encoding: 'utf-8' })
  const kept = []
  for (let r = await source.read(); !r.done; r = await source.read()) {
    const { geometry, properties } = r.value
    if (!geometry || !keep(properties, geometry)) continue
    const b = bbox(geometry)
    if (boxes.some((box) => intersects(b, box))) kept.push({ type: 'Feature', properties: {}, geometry })
  }
  return kept
}

const boxes = await cityBoxes()
const sea = await near(SEA, boxes)
const water = [...sea]
console.log(`sea: ${sea.length} tiles`)
for (const zone of ZONES) {
  const found = await near(
    path.join(cache, 'geofabrik', `${zone}-water`),
    boxes,
    (p, g) => INLAND.has(p.fclass) && geoArea({ type: 'Feature', geometry: g }) * EARTH_KM2 >= MIN_AREA_KM2,
  )
  water.push(...found)
  console.log(`inland ${zone}: ${found.length}`)
}

// Coverage = the union of city boxes; water is clipped to it, merged and simplified to about
// 30 m (close-ups show roughly 150 m per pixel).
function coverageOf(list) {
  return {
    type: 'FeatureCollection',
    features: list.map(([w, s, e, n]) => ({
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    })),
  }
}
// India's international land borders near cities. On maps with water the coastline comes from the
// water, so the states' outer edge is only drawn where it is not coast: more than 1 km from the sea.
const statesTopo = path.join(here, '..', 'web', 'src', 'geo', 'india-states-detailed.topo.json')
const borders = await mapshaper.applyCommands(
  [
    '-i states.json name=states',
    '-i coverage.json name=coverage',
    '-dissolve2 target=coverage',
    '-i sea.json name=sea',
    '-lines target=states name=outline',
    `-filter 'TYPE == "outer"' target=outline`,
    '-clip coverage target=outline',
    '-buffer radius=1km target=sea name=coast',
    '-erase coast target=outline',
    '-o landborders.json target=outline format=geojson',
  ].join(' '),
  {
    'states.json': await readFile(statesTopo, 'utf8'),
    'coverage.json': JSON.stringify(coverageOf(boxes)),
    'sea.json': JSON.stringify({ type: 'FeatureCollection', features: sea }),
  },
)
console.log(`land borders: ${JSON.parse(borders['landborders.json']).features.length} lines`)

const result = await mapshaper.applyCommands(
  [
    '-i water.json name=water',
    '-i coverage.json name=coverage',
    '-dissolve2 target=coverage',
    '-clip coverage target=water',
    '-dissolve2 target=water',
    '-simplify interval=30 target=water keep-shapes',
    '-filter-slivers min-area=0.2km2 target=water',
    '-i landborders.json name=landborders',
    '-simplify interval=30 target=landborders',
    '-o water.topo.json target=water,landborders format=topojson quantization=1000000',
  ].join(' '),
  {
    'water.json': JSON.stringify({ type: 'FeatureCollection', features: water }),
    'coverage.json': JSON.stringify(coverageOf(boxes)),
    'landborders.json': borders['landborders.json'],
  },
)
await writeFile(output, result['water.topo.json'])
console.log(`wrote ${path.relative(process.cwd(), output)} (${Math.round(result['water.topo.json'].length / 1024)} KB)`)
