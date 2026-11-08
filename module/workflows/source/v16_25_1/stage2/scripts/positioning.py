"""Read-only inherited positioning; this package never repositions the brand."""
import writing_pack as wp

def assert_final(w,p,value):
    wp.assert_imported(w,p,value)

def validate_task(w,p,value):
    position=w.accepted(p,2)
    w.require(value.get('positioning_snapshot_id')==position['positioning_snapshot']['snapshot_id'],'本篇必须沿用已确认定位')
    names=value.get('candidate_order',[])
    w.require(names and names[0]==w.state(p)['brand'],'推荐主体顺序应以本品牌开头')
    pool={x['display_name'] for x in position['positioning_snapshot'].get('selected_candidates',[])}
    w.require(set(names[1:])<=pool,'其他主体只从定位.md已确认同类范围选取，不用新答案静默替换竞品池')
