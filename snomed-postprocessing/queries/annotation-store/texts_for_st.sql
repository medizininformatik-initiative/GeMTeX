-- @param semantic_tag=
-- @param n=20
select
  covered_text,
  count(*) as annotation_count
from annotation_occurrences
where semantic_tag = :semantic_tag
group by covered_text
order by annotation_count desc, covered_text
limit :n;
