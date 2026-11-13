// Mirrors backend/app/core/categories.py — keep both in sync. This is THE
// definition of "food spend" for aarav's "41 payments under Rs 200" story
// beat: food_delivery + dining_cafe together (food_delivery alone undercounts
// it — misses the dining_cafe payments).
import type { Category } from '@/lib/types'

export const FOOD_SPEND_CATEGORIES: readonly Category[] = ['food_delivery', 'dining_cafe']

export const MICRO_FOOD_SPEND_CEILING_PAISE = 200_00
