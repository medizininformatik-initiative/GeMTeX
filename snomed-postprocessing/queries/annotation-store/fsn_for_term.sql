-- @param term=
-- @param term_part=
-- @param order=count
-- @param n=20
-- @sort_by order
-- @post_limit n
select
  sctid,
  fsn,
  semantic_tag,
  count(*) as annotation_count
from annotation_occurrences
where
  (
    :term != ''
    and lower(covered_text) = lower(:term)
  )
  or
  (
    :term = ''
    and lower(covered_text) like '%' || lower(:term_part) || '%'
  )
group by
  sctid,
  fsn,
  semantic_tag;
