-- migrate:up

-- Hindi text for indicators and thematic indices, loaded by `unnati seed` from
-- reference/hi.yaml. The site falls back to the English column where these are null.
alter table indicator
    add column description_hi text,
    add column unit_hi        text,
    add column caveat_hi      text;

alter table index_definition
    add column description_hi text,
    add column method_hi      text,
    add column caveat_hi      text,
    add column inspired_by_hi text,
    -- {"Health": "स्वास्थ्य", ...}: Hindi names of the dimensions in `components`
    add column dimensions_hi  jsonb;

-- migrate:down

alter table index_definition
    drop column dimensions_hi, drop column inspired_by_hi, drop column caveat_hi,
    drop column method_hi, drop column description_hi;
alter table indicator drop column caveat_hi, drop column unit_hi, drop column description_hi;
