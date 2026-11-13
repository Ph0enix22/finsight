"""Shared, named definitions for story-beat-shaped spend queries — kept in one
place so the backend test, and anything the frontend computes client-side
(mirrored in `frontend/src/lib/foodSpend.ts`), agree on what "food spend"
means. Don't redefine this inline elsewhere.
"""

from app.models.enums import Category

# aarav's "41 food payments under Rs 200" story beat (CLAUDE.md demo facts)
# counts both food_delivery and dining_cafe — they're kept as separate
# categories for the categoriser (see scripts/generate.py's comment on why),
# but the human-facing "food spend" story beat spans both.
FOOD_SPEND_CATEGORIES: tuple[Category, Category] = (
    Category.FOOD_DELIVERY,
    Category.DINING_CAFE,
)

# The "<Rs 200 per payment" ceiling from the same story beat, in paise.
MICRO_FOOD_SPEND_CEILING_PAISE = 200_00
