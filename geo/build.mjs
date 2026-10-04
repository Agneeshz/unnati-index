// Builds web/public/geo/india-states.topo.json: state/UT boundaries for the choropleth maps.
//
// Source: DataMeet `States/Admin2` (CC BY 4.0), pinned to the commit that aligned the J&K and
// Ladakh boundaries with the latest Survey of India map and reflects the January 2020 status
// (DNH and DD merged). Each shape is keyed by our entity slug; the build fails if any of the
// 36 current states/UTs is missing or unmatched.
import { existsSync } from 'node:fs'
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import mapshaper from 'mapshaper'

const COMMIT = '2c0c306a0c786a83876065a62b7b82646d8a639d'
const SOURCE = `https://raw.githubusercontent.com/datameet/maps/${COMMIT}/States`
const PARTS = ['Admin2.shp', 'Admin2.shx', 'Admin2.dbf', 'Admin2.prj', 'Admin2.cpg']

const here = import.meta.dirname
const cacheDir = path.join(here, 'build')
const output = path.join(here, '..', 'web', 'public', 'geo', 'india-states.topo.json')
const entitiesCsv = path.join(here, '..', 'pipeline', 'src', 'unnati', 'reference', 'entities.csv')

// Names used in the shapefile that differ from our entity names.
const NAME_FIXES = {
  'Andaman & Nicobar': 'andaman-and-nicobar-islands',
  'Jammu & Kashmir': 'jammu-and-kashmir',
  Kerala: 'keralam', // renamed by the Kerala (Alteration of Name) Act, 2026
}

const slugify = (name) =>
  name
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z]+/g, '-')
    .replace(/^-|-$/g, '')

async function download() {
  await mkdir(cacheDir, { recursive: true })
  for (const part of PARTS) {
    const file = path.join(cacheDir, part)
    if (existsSync(file)) continue
    const response = await fetch(`${SOURCE}/${part}`)
    if (!response.ok) throw new Error(`download failed for ${part}: HTTP ${response.status}`)
    await writeFile(file, Buffer.from(await response.arrayBuffer()))
  }
}

async function currentEntities() {
  const [header, ...lines] = (await readFile(entitiesCsv, 'utf8')).trim().split(/\r?\n/)
  const columns = header.split(',')
  return lines
    .map((line) => Object.fromEntries(line.split(',').map((value, i) => [columns[i], value])))
    .filter((e) => (e.type === 'state' || e.type === 'ut') && !e.valid_to)
}

await download()
const inputs = Object.fromEntries(
  await Promise.all(PARTS.map(async (part) => [part, await readFile(path.join(cacheDir, part))])),
)

// 1. Repair topology, then simplify for the web (keeping every small UT and island group), and
//    export as GeoJSON so shapes can be keyed by slug. `-clean` must run before `-simplify`:
//    run after it, it rebuilds the full-detail geometry.
const simplified = await mapshaper.applyCommands(
  '-i Admin2.shp encoding=utf8 -clean -simplify 2% weighted keep-shapes -o states.json format=geojson precision=0.00001',
  inputs,
)
const geojson = JSON.parse(simplified['states.json'])

const entities = await currentEntities()
const known = new Map(entities.map((e) => [e.slug, e]))
const seen = new Set()
for (const feature of geojson.features) {
  const sourceName = feature.properties.ST_NM
  const slug = NAME_FIXES[sourceName] ?? slugify(sourceName)
  if (!known.has(slug)) throw new Error(`shape "${sourceName}" does not match any current entity (${slug})`)
  if (seen.has(slug)) throw new Error(`more than one shape for ${slug}`)
  seen.add(slug)
  feature.properties = { slug, name: known.get(slug).name }
}
const missing = [...known.keys()].filter((slug) => !seen.has(slug))
if (missing.length) throw new Error(`no shape for: ${missing.join(', ')}`)

// 2. Convert to compact TopoJSON (shared borders stored once).
const topo = await mapshaper.applyCommands(
  '-i states.json -rename-layers states -o india-states.topo.json format=topojson quantization=100000',
  { 'states.json': JSON.stringify(geojson) },
)
await mkdir(path.dirname(output), { recursive: true })
await writeFile(output, topo['india-states.topo.json'])
const { size } = await stat(output)
console.log(`wrote ${path.relative(process.cwd(), output)}: ${seen.size} states/UTs, ${(size / 1024).toFixed(0)} KB`)
