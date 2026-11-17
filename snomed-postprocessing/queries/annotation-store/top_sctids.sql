-- @param n=50
select
  sctid,
  semantic_tag,
  fsn,
  count(*) as annotation_count
from annotations
group by sctid, semantic_tag, fsn
order by annotation_count desc, sctid
limit :n;
