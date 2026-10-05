# Methodology (v1.1)

This describes how the Unnati Index scores and ranks states. Every change is versioned: a new
version keeps the previous goalposts for the indicators it doesn't change, recomputes all
editions, and is logged under [Changes](#changes) below and on the site's methodology page.

## What gets ranked

- **36 current states and Union Territories**, in three peer groups that follow NITI Aayog's
  practice: 18 large states (including Goa), 10 North-East and Himalayan states, and 8 UTs.
  Ranks are shown within each peer group and overall.
- **Only rates, shares and per-person values.** Raw totals (GSDP, exports, population) are shown
  for context but never ranked, so states don't win or lose just by size.
- Boundary changes (Andhra Pradesh/Telangana 2014, J&K/Ladakh 2019, DNH + DD 2020) create
  separate entities. Time series show a break rather than inventing continuity.

## The composite: 8 pillars, 44 indicators

| Pillar | Indicators |
|---|---|
| Economy & Jobs | real per-capita income, 3-year real GSDP growth, unemployment rate, workers in regular salaried jobs, merchandise exports per person |
| Health | infant mortality, maternal mortality, life expectancy, child stunting, anaemia in women, full immunisation |
| Education | secondary GER, secondary dropout, secondary pupil–teacher ratio, schools with computers, PARAKH learning outcomes (Grades 3, 6 and 9), higher-education GER |
| Safety & Justice | murder rate, road deaths per lakh, conviction rate, criminal trials pending, police vacancy rate, court cases pending over 5 years (no data yet) |
| Governance & Fiscal Health | fiscal deficit, debt, own tax revenue (all % of GSDP), capital expenditure share |
| Infrastructure & Digital | rural tap water, per-capita electricity, clean cooking fuel, improved sanitation, internet subscribers per 100 |
| Environment | annual PM2.5, forest cover change, renewable share of capacity, groundwater extraction stage, urban waste processed |
| Inclusion & Equality | multidimensional poverty, sex ratio at birth, female labour force participation, women's bank-account use, child marriage, consumption inequality, violence against women by husbands (NFHS) |

Each pillar has 4–7 indicators, each measuring something different, with equal weights. Variants
of an indicator already used, close duplicates, and measures that mislead when ranked are shown on
the site for context but kept out of the pillars.

The full definitions, units, sources and caveats are in
[`pipeline/src/unnati/reference/indicators.yaml`](../pipeline/src/unnati/reference/indicators.yaml).

**Why murder rate and not total crime?** Registered crime depends on how easily people can report
it, so a higher rate can mean better reporting. Murder is the crime least affected by
under-reporting. Other crime indicators are shown with that caveat but kept out of the composite.

**Why spousal violence (NFHS) and not registered crimes against women?** Registered crimes against
women are highest where reporting is easiest (Delhi, Telangana, Kerala) and lowest in states such
as Nagaland and Manipur, so ranking on them would reward under-reporting. NFHS asks women
privately, in the same way in every state, so it counts violence that never reaches the police.
It covers violence by husbands only.

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

## Changes

- **1.1 (5 October 2026).** The Inclusion pillar adds violence against women by their husbands
  (NFHS-5, moving to NFHS-6 once 80% of states have readable figures). The Gender Equality and
  Social Progress indices use it instead of registered crimes against women; the Safety Index
  keeps registered crime. Pillars may now have up to 7 indicators. All other goalposts are carried
  over from 1.0, so only this change moves the scores: Andhra Pradesh moves from 8th to 9th among
  large states, and Assam's score falls from 50.0 to 49.3.
- **1.0 (4 October 2026).** First published version: fixed goalposts, 8 equal-weight pillars.
