-- migrate:up

-- Thematic indices built from the same indicators as the Unnati Index (an HDI-style estimate,
-- social progress, safety, gender equality, child well-being). Their scores live in `score`
-- with level 'composite' and key = index id.
create table index_definition (
    id          text primary key,
    name        text not null,
    name_hi     text,
    description text not null,
    method      text not null,
    caveat      text,
    inspired_by text,
    -- [{"dimension": "Health", "indicators": ["life-expectancy"]}, ...] in display order
    components  jsonb not null,
    sort        smallint not null
);

-- Indicators used only by thematic indices need goalposts too, without belonging to a pillar.
alter table methodology_indicator alter column pillar_id drop not null;

-- migrate:down

delete from methodology_indicator where pillar_id is null;
alter table methodology_indicator alter column pillar_id set not null;
drop table index_definition;
