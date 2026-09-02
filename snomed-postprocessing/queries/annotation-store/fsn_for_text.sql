-- @param covered_text=
-- @param covered_text_part=
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
    :covered_text != ''
    and lower(covered_text) = lower(:covered_text)
  )
  or
  (
    :covered_text = ''
    and lower(covered_text) like '%' || lower(:covered_text_part) || '%'
  )
group by
  sctid,
  fsn,
  semantic_tag;
