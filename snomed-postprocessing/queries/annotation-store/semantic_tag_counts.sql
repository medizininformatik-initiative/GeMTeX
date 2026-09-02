-- @param order=count
-- @sort_by order
-- @param n=20
-- @post_limit n
select
    semantic_tag,
    count(*) as annotation_count
from annotation_occurrences
group by semantic_tag;
