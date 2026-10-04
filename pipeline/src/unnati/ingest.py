"""Run a dataset's connector end to end: fetch, convert, validate, load, record.

Each ingester returns observations plus non-fatal problems (e.g. an unknown place name) and a
fingerprint of the raw fetch; this module does the rest identically for every source."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from unnati import observations as obs
from unnati.db import Connection
from unnati.reference import load_reference
from unnati.runs import finish_run, last_fingerprint, mark_checked, start_run


@dataclass
class Fetched:
    observations: list[obs.Observation]
    problems: list[str]
    fingerprint: str
    source_url: str


@dataclass
class IngestReport:
    dataset_id: str
    fetched: Fetched
    validation: obs.Validation
    status: str = "dry-run"
    counts: dict[str, int] = field(default_factory=dict)


def fingerprint_of(raw: object) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()


def _mospi_nas_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_nas_state(http)
    observations, problems = mospi.nas_observations(rows, load_reference().resolver(), today)
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/nas/getNASData")


def _mospi_plfs_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_plfs_state(http)
        status = mospi.fetch_plfs_status(http)
    resolver = load_reference().resolver()
    observations, problems = mospi.plfs_observations(rows, resolver)
    extra, more = mospi.plfs_status_observations(status, resolver)
    raw = {"series": rows, "status": status}
    return Fetched(
        observations + extra, problems + more, fingerprint_of(raw), f"{mospi.BASE_URL}/api/plfs/getData"
    )


def _mospi_cpi_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_cpi_state(http)
    observations, problems = mospi.cpi_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/cpi/getCPIIndex")


def _mospi_nfhs(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_nfhs_state(http)
    observations, problems = mospi.nfhs_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/nfhs/getNfhsRecords")


def _udise_plus(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_udise_state(http)
    observations, problems = mospi.udise_observations(rows, load_reference().resolver(), today)
    raw = {f"{code}:{filters}": value for (code, filters), value in rows.items()}
    return Fetched(observations, problems, fingerprint_of(raw), f"{mospi.BASE_URL}/api/udise/getUdiseRecords")


def _aishe(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_aishe_ger(http)
    observations, problems = mospi.aishe_observations(rows, load_reference().resolver(), today)
    return Fetched(
        observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/aishe/getAisheRecords"
    )


def _mospi_hces(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_hces_gini(http)
    observations, problems = mospi.hces_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/hces/getHcesRecords")


def _mospi_envstats(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_envstats(http)
    from unnati.reference import population

    observations, problems = mospi.envstats_observations(rows, load_reference().resolver(), population())
    raw = {str(code): value for code, value in rows.items()}
    return Fetched(
        observations, problems, fingerprint_of(raw), f"{mospi.BASE_URL}/api/env/getEnvStatsRecords"
    )


def _cpcb_aqi_bulletin(today: date) -> Fetched:
    import os

    from unnati.connectors import cpcb_bulletin
    from unnati.core.http import PoliteClient

    days = int(os.environ.get("UNNATI_AQI_DAYS", cpcb_bulletin.WINDOW_DAYS))  # larger for a backfill
    with PoliteClient(timeout=60) as http:
        bulletins = cpcb_bulletin.fetch(http, today, days)
    observations, problems = cpcb_bulletin.observations(bulletins)
    raw = {str(d): hashlib.sha256(b).hexdigest() for d, b in bulletins.items()}
    return Fetched(
        observations,
        problems,
        fingerprint_of(raw),
        cpcb_bulletin.URL.format(day=max(bulletins, default=today)),
    )


def _phonepe_pulse(today: date) -> Fetched:
    from unnati.connectors import phonepe
    from unnati.core.http import PoliteClient
    from unnati.reference import population

    with PoliteClient(timeout=60) as http:
        quarters = phonepe.fetch(http, today)
    observations, problems = phonepe.observations(quarters, load_reference().resolver(), population())
    raw = {f"{y}-{q}": v for (y, q), v in quarters.items()}
    return Fetched(observations, problems, fingerprint_of(raw), "https://github.com/PhonePe/pulse")


def _gstn_state_collections(today: date) -> Fetched:
    from unnati.connectors import gstn
    from unnati.core.http import PoliteClient
    from unnati.reference import population

    with PoliteClient(timeout=120) as http:
        urls = gstn.report_urls(http)
        reports = [http.get(url).content for url in urls]
    observations, problems = gstn.observations(reports, load_reference().resolver(), population())
    raw = {url: hashlib.sha256(pdf).hexdigest() for url, pdf in zip(urls, reports, strict=True)}
    return Fetched(observations, problems, fingerprint_of(raw), gstn.NEWS)


def _jjm_tap_water(today: date) -> Fetched:
    """Reads the committed dashboard exports (pipeline/manual-downloads/jjm/)."""
    from unnati.connectors import jjm

    files = {path.name: path.read_bytes() for path in sorted(jjm.MANUAL_DIR.glob("*.pdf"))}
    if not files:
        raise RuntimeError(f"no JJM exports in {jjm.MANUAL_DIR}")
    observations, problems = jjm.observations(files, load_reference().resolver())
    raw = {name: hashlib.sha256(pdf).hexdigest() for name, pdf in files.items()}
    url = "https://ejalshakti.gov.in/jjmreport/JJMIndia.aspx"
    return Fetched(observations, problems, fingerprint_of(raw), url)


def _parakh(today: date) -> Fetched:
    """NCERT's state reports (about 2.7 MB each); PRS 2024 is a one-off, so not on the schedule."""
    from unnati.connectors import parakh
    from unnati.core.http import PoliteClient

    reports, problems = {}, []
    with PoliteClient(timeout=120) as http:
        for e in load_reference().entities:
            if e.type not in ("state", "ut") or e.valid_to or not e.lgd_code:
                continue
            url = parakh.report_url(http, e.slug, e.name, int(e.lgd_code))
            if url is None:
                problems.append(f"PARAKH: no state report found for {e.name}")
                continue
            reports[e.slug] = http.get(url).content
    observations, more = parakh.observations(reports)
    raw = {slug: hashlib.sha256(pdf).hexdigest() for slug, pdf in reports.items()}
    url = "https://parakh.ncert.gov.in/prs-reports-2024"
    return Fetched(observations, problems + more, fingerprint_of(raw), url)


def _aai_traffic(today: date) -> Fetched:
    from unnati.connectors import aai
    from unnati.core.http import PoliteClient
    from unnati.reference import population

    with PoliteClient(timeout=120) as http:
        month_end, url = aai.latest_report(http)
        pdf = http.get(url).content
    observations, problems = aai.observations(aai.passengers(pdf), month_end, population())
    return Fetched(observations, problems, fingerprint_of({"url": url, "sha": hashlib.sha256(pdf).hexdigest()}), url)


def _rbi_hsis(today: date) -> Fetched:
    """Reads the committed downloads; MoSPI's GSDP fills in where RBI Table 21 is absent."""
    from unnati.connectors import mospi, rbi_hsis
    from unnati.reference import population

    folders = sorted(p.name for p in rbi_hsis.MANUAL_DIR.glob("*-*") if p.is_dir())
    if not folders:
        raise RuntimeError(f"no RBI handbook downloads in {rbi_hsis.MANUAL_DIR}")
    edition = folders[-1]
    files = rbi_hsis.local_files(edition)
    gsdp: dict[tuple[str, str], float] = {}
    covered: set[str] = set()
    if 21 not in files or 20 in files or 22 in files:
        # MoSPI's GSDP (when Table 21 is missing) and the places MoSPI already covers, so RBI's
        # per-capita income and growth only fill the gaps.
        with mospi.client() as http:
            rows = mospi.fetch_nas_state(http)
        nas, _ = mospi.nas_observations(rows, load_reference().resolver(), today)
        gsdp = {(o.entity_slug, o.period.label): o.value for o in nas if o.indicator_id == "gsdp-current"}
        covered = {o.entity_slug for o in nas if o.indicator_id == "per-capita-nsdp-constant"}
    observations, problems = rbi_hsis.observations(
        files, edition, load_reference().resolver(), population(), gsdp, covered
    )
    raw = {n: hashlib.sha256(path.read_bytes()).hexdigest() for n, path in sorted(files.items())}
    # The files rarely change, so the parser's own code is part of the fingerprint: a fix to the
    # importer reprocesses the same files instead of being skipped as "unchanged".
    parser = hashlib.sha256(Path(rbi_hsis.__file__).read_bytes()).hexdigest()
    fingerprint = fingerprint_of({"edition": edition, "files": raw, "parser": parser})
    return Fetched(observations, problems, fingerprint, rbi_hsis.INDEX_URL)


def _nfhs_factsheets(today: date) -> Fetched:
    from unnati.connectors import nfhs_factsheets as nf
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=300) as http:
        pdf, csvs = nf.fetch(http)
    observations, problems = nf.observations(pdf, csvs, load_reference().resolver())
    raw = {"pdf": hashlib.sha256(pdf).hexdigest(), "csvs": csvs}
    return Fetched(observations, problems, fingerprint_of(raw), nf.PDF_URL)


def _ncrb_fingerprint(found, local: dict[int, dict[int, bytes]]) -> str:
    from unnati.connectors import ncrb

    hashes = {f"{y}:{v}": hashlib.sha256(b).hexdigest() for y, vols in local.items() for v, b in vols.items()}
    return fingerprint_of({"opencity": ncrb.fingerprint(found), "local": hashes})


def _ncrb_probe(today: date) -> str:
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        return _ncrb_fingerprint(ncrb.editions(http, today), ncrb.local_volumes())


def _ncrb_cii(today: date) -> Fetched:
    """OpenCity's mirror, plus hand-downloaded volumes (Volume 3) from the repo."""
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    local = ncrb.local_volumes()
    with PoliteClient(timeout=300) as http:
        found = ncrb.editions(http, today)
        pdfs = ncrb.fetch(http, found)
    for year, volumes in local.items():
        pdfs.setdefault(year, {}).update(volumes)
    observations, problems = ncrb.observations(pdfs, load_reference().resolver())
    latest = found[-1]
    url = latest.volumes.get(1, ncrb.CKAN_PACKAGE)
    return Fetched(observations, problems, _ncrb_fingerprint(found, local), url)


def _ncrb_adsi(today: date) -> Fetched:
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=120) as http:
        tables = ncrb.adsi_tables(http, today)
        pdfs = {year: http.get(resource["url"]).content for year, resource in tables.items()}
    observations, problems = ncrb.adsi_observations(pdfs, load_reference().resolver())
    raw = {year: hashlib.sha256(pdf).hexdigest() for year, pdf in pdfs.items()}
    return Fetched(observations, problems, fingerprint_of(raw), tables[max(tables)]["url"])


def _srs_probe(today: date) -> str:
    from unnati.connectors import srs
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        return srs.fingerprint(*srs.latest_resource(http))


def _rgi_srs(today: date) -> Fetched:
    from unnati.connectors import srs
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=300) as http:
        edition, resource = srs.latest_resource(http)
        pdf = http.get(resource["url"]).content
    observations, problems = srs.observations(pdf, edition, load_reference().resolver())
    return Fetched(observations, problems, srs.fingerprint(edition, resource), resource["url"])


def _srs_bulletin(series_name: str) -> tuple[Callable[[date], str], Callable[[date], Fetched]]:
    """Probe and ingester for one SRS bulletin series (MMR or LIFE)."""

    def probe(today: date) -> str:
        from unnati.connectors import srs_bulletins as sb

        with sb.client() as http:
            return sb.fingerprint(sb.editions(http, getattr(sb, series_name)))

    def ingest(today: date) -> Fetched:
        from unnati.connectors import srs_bulletins as sb

        with sb.client() as http:
            found = sb.editions(http, getattr(sb, series_name))
            pdfs = [(edition, sb.download(http, edition)) for edition in found]
        observations, problems = sb.observations(pdfs, load_reference().resolver())
        url = f"{sb.NADA}/catalog/{found[-1].catalog_id}"
        return Fetched(observations, problems, sb.fingerprint(found), url)

    return probe, ingest


_srs_mmr_probe, _srs_mmr = _srs_bulletin("MMR")
_srs_life_probe, _srs_life = _srs_bulletin("LIFE")


def _trai_probe(today: date) -> str:
    from unnati.connectors import trai
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        return trai.fingerprint(trai.report_urls(http))


def _trai_subscriptions(today: date) -> Fetched:
    from unnati.connectors import trai
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=300) as http:
        urls = trai.report_urls(http)
        pdfs = [http.get(url).content for url in urls]
    observations, problems = trai.observations(pdfs, load_reference().resolver())
    return Fetched(observations, problems, trai.fingerprint(urls), urls[0])


def _bprd_dopo(today: date) -> Fetched:
    from unnati.connectors import bprd
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=600) as http:
        year, url = bprd.latest(http)
        pdf = http.get(url).content
    observations, problems = bprd.observations(pdf, year, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of({"year": year, "url": url}), url)


def _bprd_probe(today: date) -> str:
    from unnati.connectors import bprd
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        year, url = bprd.latest(http)
    return fingerprint_of({"year": year, "url": url})


def _morth_road_accidents(today: date) -> Fetched:
    from unnati.connectors import morth
    from unnati.core.http import PoliteClient
    from unnati.reference import population

    with PoliteClient(timeout=120) as http:
        edition, resource = morth.latest(http, today)
        text = http.get(resource["url"]).text
    observations, problems = morth.observations(text, edition, load_reference().resolver(), population())
    return Fetched(observations, problems, fingerprint_of({"edition": edition, "csv": text}), resource["url"])


def _population_projections(today: date) -> Fetched:
    from unnati.connectors import population_projections as pp
    from unnati.core.periods import calendar_year
    from unnati.reference import population

    # Projections run to 2036; only years up to now are loaded, so "latest" means this year.
    rows = {key: value for key, value in population().items() if key[1] <= today.year}
    observations = [
        obs.Observation(
            "population", slug, calendar_year(year), value.persons, note="Projected population as on 1 July"
        )
        for (slug, year), value in sorted(rows.items())
    ]
    raw = {f"{slug}:{year}": value.persons for (slug, year), value in rows.items()}
    return Fetched(observations, [], fingerprint_of(raw), pp.REPORT_URL)  # changes each new year


INGESTERS: dict[str, Callable[[date], Fetched]] = {
    "mospi_nas_state": _mospi_nas_state,
    "mospi_plfs_state": _mospi_plfs_state,
    "mospi_cpi_state": _mospi_cpi_state,
    "mospi_nfhs": _mospi_nfhs,
    "udise_plus": _udise_plus,
    "aishe": _aishe,
    "mospi_hces": _mospi_hces,
    "mospi_envstats": _mospi_envstats,
    "cpcb_aqi_bulletin": _cpcb_aqi_bulletin,
    "phonepe_pulse": _phonepe_pulse,
    "gstn_state_collections": _gstn_state_collections,
    "jjm_tap_water": _jjm_tap_water,
    "parakh": _parakh,
    "aai_traffic": _aai_traffic,
    "rbi_hsis": _rbi_hsis,
    "nfhs": _nfhs_factsheets,  # on demand: a 49 MB one-off release, not on the daily schedule
    "ncrb_cii": _ncrb_cii,
    "ncrb_adsi": _ncrb_adsi,
    "morth_road_accidents": _morth_road_accidents,
    "rgi_srs": _rgi_srs,
    "trai_subscriptions": _trai_subscriptions,
    "bprd_dopo": _bprd_dopo,
    "rgi_srs_mmr": _srs_mmr,
    "rgi_srs_life_tables": _srs_life,
    "population_projections": _population_projections,
}

# Cheap change checks for sources that are expensive to download: when the probe's fingerprint
# matches the last load, the run stops before fetching. The ingester must report the same
# fingerprint as its probe.
PROBES: dict[str, Callable[[date], str]] = {
    "ncrb_cii": _ncrb_probe,
    "rgi_srs": _srs_probe,
    "trai_subscriptions": _trai_probe,
    "bprd_dopo": _bprd_probe,
    "rgi_srs_mmr": _srs_mmr_probe,
    "rgi_srs_life_tables": _srs_life_probe,
}


def check(dataset_id: str, today: date) -> IngestReport:
    """Fetch and validate without touching the database."""
    if dataset_id not in INGESTERS:
        raise KeyError(f"no ingester for {dataset_id!r}; available: {', '.join(sorted(INGESTERS))}")
    fetched = INGESTERS[dataset_id](today)
    ref = load_reference()
    current = [e for e in ref.entities if e.type in ("state", "ut") and e.valid_to is None]
    validation = obs.validate(
        fetched.observations,
        {i.id: i for i in ref.indicators},
        current_places=len(current),
        entity_types={e.slug: e.type for e in ref.entities},
    )
    return IngestReport(dataset_id, fetched, validation)


def run(
    conn: Connection, dataset_id: str, today: date, trigger: str = "manual", force: bool = False
) -> IngestReport:
    run_id = start_run(conn, dataset_id, trigger)
    try:
        if dataset_id in PROBES and not force:
            probed = PROBES[dataset_id](today)
            if probed == last_fingerprint(conn, dataset_id):
                mark_checked(conn, dataset_id, probed, changed=False)
                finish_run(conn, run_id, "unchanged", fingerprint=probed)
                return IngestReport(dataset_id, Fetched([], [], probed, ""), obs.Validation(), "unchanged")
        report = check(dataset_id, today)
        details = {**report.validation.as_dict(), "problems": report.fetched.problems}
        if not report.validation.ok:
            report.status = "rejected"
            finish_run(conn, run_id, "rejected", validation=details, source_url=report.fetched.source_url)
            return report
        fingerprint = report.fetched.fingerprint
        if fingerprint == last_fingerprint(conn, dataset_id) and not force:
            mark_checked(conn, dataset_id, fingerprint, changed=False)
            finish_run(
                conn, run_id, "unchanged", fingerprint=fingerprint, source_url=report.fetched.source_url
            )
            report.status = "unchanged"
            return report
        report.counts = obs.load(conn, report.fetched.observations, run_id)
        mark_checked(conn, dataset_id, fingerprint, changed=True)
        finish_run(
            conn,
            run_id,
            "loaded",
            rows_loaded=report.counts["new"] + report.counts["revised"],
            fingerprint=fingerprint,
            source_url=report.fetched.source_url,
            validation=details,
        )
        report.status = "loaded"
        return report
    except Exception as err:
        finish_run(conn, run_id, "failed", error=str(err))
        raise
