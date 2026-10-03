# Methodology (draft v1)

This describes how the Unnati Index will score and rank states. It is a draft: goalposts are set
once enough data is loaded, and every change after publication is versioned and logged.

## What gets ranked

- **36 current states and Union Territories**, in three peer groups that follow NITI Aayog's
  practice: 18 large states (including Goa), 10 North-East and Himalayan states, and 8 UTs.
  Ranks are shown within each peer group and overall.
- **Only rates, shares and per-person values.** Raw totals (GSDP, exports, population) are shown
  for context but never ranked, so states don't win or lose just by size.
- Boundary changes (Andhra Pradesh/Telangana 2014, J&K/Ladakh 2019, DNH + DD 2020) create
  separate entities. Time series show a break rather than inventing continuity.

## The composite: 8 pillars, 42 indicators

| Pillar | Indicators |
|---|---|
| Economy & Jobs | real per-capita income, 3-year real GSDP growth, unemployment rate, merchandise exports per person, new formal jobs (EPFO) per 1,000 working-age people |
| Health | infant mortality, maternal mortality, life expectancy, child stunting, anaemia in women, full immunisation |
| Education | secondary GER, secondary dropout, secondary pupil–teacher ratio, schools with internet, PARAKH Grade 6 maths, higher-education GER |
| Safety & Justice | murder rate, road deaths per lakh, conviction rate, court cases pending over 5 years, police vacancy rate |
| Governance & Fiscal Health | fiscal deficit, debt, own tax revenue (all % of GSDP), capital expenditure share |
| Infrastructure & Digital | rural tap water, per-capita electricity, clean cooking fuel, improved sanitation, internet subscribers per 100 |
| Environment | annual PM2.5, forest cover change, renewable share of capacity, groundwater extraction stage, urban waste processed |
| Inclusion & Equality | multidimensional poverty, sex ratio at birth, female labour force participation, women's bank-account use, child marriage, consumption inequality |

The full definitions, units, sources and caveats are in
[`pipeline/src/unnati/reference/indicators.yaml`](../pipeline/src/unnati/reference/indicators.yaml).

**Why murder rate and not total crime?** Registered crime depends on how easily people can report
it, so a higher rate can mean better reporting. Murder is the crime least affected by
under-reporting. Other crime indicators are shown with that caveat but kept out of the composite.

## Scoring

1. **Normalise each indicator to 0–100 with fixed goalposts.** This is the approach of NITI
   Aayog's SDG India Index. The "best" goalpost is the national or SDG target where one exists
   (e.g. MMR 70, full immunisation 100%), otherwise the 97.5th-percentile best value. The "worst"
   goalpost is the 2.5th-percentile worst value since 2015. For "lower is better" indicators the
   direction is flipped. Values beyond a goalpost are clipped.
   Because goalposts are fixed, a state's score changes only when its own value changes.
2. **Pillar score** = mean of its indicator scores, computed only when at least two-thirds of the
   pillar's indicators have data. Gaps are never filled silently.
3. **Unnati Index score** = mean of the eight pillar scores, computed only when at least six
   pillars have scores. Bands: Achiever (100), Front Runner (65–99), Performer (50–64),
   Aspirant (below 50).
4. **Editions.** Each yearly edition uses the latest value of every indicator published by its
   cut-off date, ignoring values more than five years old. The year of each value is shown.
5. **Ranks** use standard competition ranking; scores equal to one decimal place tie.
6. **Most improved** compares a state's score with its score three editions earlier under the
   same methodology version.
7. **Uncertainty.** For survey-based indicators (NFHS, PLFS) confidence intervals are stored, and
   comparisons say "statistically tied" when intervals overlap.

Readers can re-weight pillars on the rankings page; the published index uses equal weights.

## Leadership and accountability

Each state shows its office-holders: Governor or Lieutenant Governor, Chief Minister, Deputy Chief
Ministers, the ministers whose portfolios match each category, the Chief Secretary, the DGP and
the relevant department secretaries. Every figure is linked to the people **in office during the
period it describes**. NCRB 2024 data, for example, is shown with the 2024 office-holders, not
today's. Information is factual (name, office, tenure, party for political offices, source and
date verified). Affidavit details are linked to ADR/MyNeta and the ECI rather than copied.
There are no party-versus-party leaderboards.

## Freshness

Every dataset declares its release cadence in the
[registry](../pipeline/src/unnati/registry.yaml). The pipeline checks sources daily (air quality
hourly), loads new releases automatically, keeps every revision, and flags a dataset when it is
overdue by half its cadence or more. The site's sources page will show each dataset's status.
