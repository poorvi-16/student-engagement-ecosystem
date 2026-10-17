from fastapi import APIRouter

from app.catalog import get_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/meta")
def catalog_meta() -> dict:
    """Options for the quiz and other forms (public, no auth)."""
    cat = get_catalog()
    return {
        "countries": sorted(cat.meta["countries"]),
        "fields": cat.meta["fields"],
        "university_count": len(cat.universities),
        "course_count": len(cat.courses),
        "disclaimer": cat.meta["disclaimer"],
    }
