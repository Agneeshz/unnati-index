-- migrate:up

-- Cities are drawn on maps and sized by population (reference/cities.csv).
alter table entity
    add column latitude        double precision,
    add column longitude       double precision,
    add column population_2011 integer;

-- migrate:down

alter table entity drop column population_2011, drop column longitude, drop column latitude;
