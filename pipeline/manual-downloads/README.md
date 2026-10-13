# Manual downloads

Official files that the pipeline cannot fetch itself because the publisher's file server shows
a browser challenge (the challenge is never bypassed). Download them in a browser, keep the
file names, and commit them; the importers read them from here.

| Folder | What | How to get the links |
|---|---|---|
| `rbi_hsis/<edition>/` | RBI *Handbook of Statistics on Indian States*, one XLSX per table (`164T_….XLSX`) | `uv run unnati manual rbi-links` |
| `jjm/` | Jal Jeevan Mission "Status of households with tap water connection" table, exported to PDF | ejalshakti.gov.in/jjmreport/JJMIndia.aspx → export the state table |
| `bprd/` | BPR&D *Data on Police Organizations* PDF, named with its year (`Data on Police Organizations (2024).pdf`). Only needed while bprd.nic.in is unreachable from GitHub's servers | bprd.nic.in → Data on Police Organisations (DoPO) |
| `ncrb_cii/<year>/` | NCRB *Crime in India*, Volume 3 PDF (court disposal, conviction rates) | ncrb.gov.in → Crime in India → year → Volume 3 |
| `lgd/` | Local Government Directory district list (CSV), the roster of current districts with LGD codes | lgdirectory.gov.in → Download Directory → Districts → "All Districts of India" (or each state) → CSV (needs the captcha) |
| `nfhs5_districts/` | NFHS-5 (2019-21) district fact sheets as one table (CSV) | data.gov.in → "India Districts Factsheets of National Family Health Survey (NFHS) - 5, 2019-2021" → Download CSV |

All files are public government publications, reproduced with attribution (see the registry).
