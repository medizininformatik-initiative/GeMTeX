-- @param semantic_tag=
-- @param semantic_tag_part=
-- @param partial_binning=false
-- @param bin_by_sctid=false
-- @param n=20
-- @partial_bin covered_text_bin
-- @post_limit n
select
  semantic_tag,
  case when lower(:bin_by_sctid) in ('1', 'true', 'yes', 'on') then sctid else null end as sctid,
  case when lower(:bin_by_sctid) in ('1', 'true', 'yes', 'on') then fsn else null end as fsn,
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
group by
  semantic_tag,
  case when lower(:bin_by_sctid) in ('1', 'true', 'yes', 'on') then sctid else null end,
  case when lower(:bin_by_sctid) in ('1', 'true', 'yes', 'on') then fsn else null end,
  lower(covered_text)
order by annotation_count desc, semantic_tag, sctid, covered_text_bin;
