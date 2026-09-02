-- @param semantic_tag=
-- @param semantic_tag_part=
-- @param partial_binning=false
-- @param n=20
-- @partial_bin covered_text_bin
-- @post_limit n
select
  semantic_tag,
  lower(covered_text) as covered_text_bin,
  group_concat(distinct covered_text) as covered_text_variants,
  count(*) as annotation_count
from annotation_occurrences
where
  (
    :semantic_tag != ''
    and lower(semantic_tag) = lower(:semantic_tag)
  )
  or
  (
    :semantic_tag = ''
    and lower(semantic_tag) like '%' || lower(:semantic_tag_part) || '%'
  )
group by semantic_tag, lower(covered_text)
order by annotation_count desc, semantic_tag, covered_text_bin;
