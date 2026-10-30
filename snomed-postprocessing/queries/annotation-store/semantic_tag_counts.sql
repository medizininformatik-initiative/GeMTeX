-- @param order=count
-- @sort_by order
-- @param n=20
-- @post_limit n
select
    semantic_tag,
    count(*) as annotation_count
from annotations
group by semantic_tag;
