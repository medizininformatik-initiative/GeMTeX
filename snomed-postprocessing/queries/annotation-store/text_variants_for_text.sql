-- @param covered_text=
-- @param covered_text_part=
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
    :covered_text != ''
    and lower(covered_text) = lower(:covered_text)
  )
  or
  (
    :covered_text = ''
    and lower(covered_text) like '%' || lower(:covered_text_part) || '%'
  )
group by
  lower(covered_text),
  semantic_tag;
