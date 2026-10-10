"""Promo drafts: the social service token may prepare a draft, never publish or delete one."""
from src.auth.admin_auth import get_admin_access, get_social_access
from src.routers.social import promo_router


def test_service_token_can_draft_promos_but_never_publish_or_delete():
    gate = {(route.path, method): {d.call for d in route.dependant.dependencies}
            for route in promo_router.routes for method in route.methods}
    drafting = [("/media", "POST"), ("/drafts", "GET"), ("/drafts", "POST"),
                ("/drafts/{draft_id}", "GET"), ("/drafts/{draft_id}", "PUT")]
    for path, method in drafting:
        assert get_social_access in gate[(f"/api/admin/promo{path}", method)], (path, method)
    for path, method in [("/publish", "POST"), ("/drafts/{draft_id}", "DELETE")]:
        assert get_admin_access in gate[(f"/api/admin/promo{path}", method)], (path, method)
