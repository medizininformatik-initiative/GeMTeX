-- @param term=
-- @param term_part=
-- @param order=count
-- @param n=50
-- @sort_by order
-- @post_limit n
select
  lower(covered_text) as covered_text_bin,
  group_concat(distinct covered_text) as covered_text_variants,
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
  lower(covered_text),
  semantic_tag;
