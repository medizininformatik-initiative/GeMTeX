select
    semantic_tag,
    count(*) as annotation_count
from annotation_occurrences
group by semantic_tag
order by annotation_count desc, semantic_tag;