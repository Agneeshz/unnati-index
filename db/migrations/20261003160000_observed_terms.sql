-- migrate:up

-- "observed" terms come from lists of current office-holders (e.g. Chief Secretaries, DGPs) for
-- which no official dated record is available. A term starts on the date the pipeline first saw
-- the person in office and ends when it first sees someone else; earlier history is not invented.
alter table office_term drop constraint office_term_source_type_check;
alter table office_term add constraint office_term_source_type_check
    check (source_type in ('wikidata', 'curated', 'official', 'observed'));

-- migrate:down

delete from office_term where source_type = 'observed';
alter table office_term drop constraint office_term_source_type_check;
alter table office_term add constraint office_term_source_type_check
    check (source_type in ('wikidata', 'curated', 'official'));
