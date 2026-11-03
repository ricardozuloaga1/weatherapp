# Avatar and wardrobe setup

The main experience is photo/camera → generated preview → explicit approval → six weather outfit choices → save → live weather. A new photo creates a separate candidate. Approval activates it and starts its wardrobe; existing avatars and their preferences remain available under Photo & profiles. Location is shared across profiles.

The wardrobe uses photographs from the owner's saved looks, uploaded complete-outfit photos, and two public UNIQLO catalog references. Each weather category has its own selection. The selected reference is submitted as the product image to FASHN tryon-max, alongside the approved avatar as the model image. Identity retention is probabilistic; the prompt asks for the same face, body, pose and framing. This is not a locked 3D identity or a guarantee of exact garment reproduction.

Save persists all six selections, then shows live weather. It reuses an explicitly selected saved look already on the active avatar without calling FASHN. Otherwise it requests only the current weather's missing outfit, reserving 3 credits. Other scenarios are generated on explicit request; repeated identical requests reuse the job cache. If there is no location, city selection completes this sequence. Weather failures preserve the wardrobe and leave a manual retry. Saving does not generate six outfits.

Local launch limits are 100 credits, matching the existing purchased top-up. This is a local cumulative request budget, not a live provider balance. No automatic purchase occurs.

## Starter photograph provenance

Local pilot references only; production requires a licensed catalog/feed agreement. No retailer partnership or API integration is implied.

- `static/images/outfits/linen.jpg`: https://www.uniqlo.com/uk/en/products/E473791-000/00 — downloaded from https://image.uniqlo.com/UQ/ST3/gb/imagesgoods/473791/item/gbgoods_30_473791_3x4.jpg
- `static/images/outfits/parka.jpg`: https://www.uniqlo.com/sg/en/products/E460924-000 — downloaded from https://image.uniqlo.com/UQ/ST3/AsianCommon/imagesgoods/460924/sub/goods_460924_sub7_3x4.jpg?width=494

The starter selection is deliberately small. Users can add complete outfit photos; no waterproof-performance claims are inferred from a photograph.

## Validation

`python -m unittest discover -s tests -q` covers approval, per-avatar restoration, complete selections, owner isolation, source-photo validation, starter allowlisting, full-outfit generation with a fake provider, exact job reuse, and zero-charge reuse of selected existing looks. Browser checks cover the saved avatar preview, approval action availability, all six selections, save-button gating, and live weather navigation. Tests do not spend provider credits.

## Expanded photographic wardrobe (November 3)

`outfit_catalog.json` now supplies the public catalog, including image provenance, weather categories, style labels, and cropped-reference notes. These are real UNIQLO retailer photos for the private prototype, not a licensed production feed. Photos are hosted locally to avoid broken external thumbnails and third-party image requests in the browser. Catalog styles include casual, minimalist, smart casual, tailored, streetwear, sporty, expressive, and classic. Coverage varies with weather. Cropped references are labeled; the generation prompt preserves the avatar's footwear when the reference doesn't show shoes.

`weather_options` stores a nonempty list of favorites per weather, independently per avatar. `weather_outfits` retains the currently active choice, maintaining compatibility with existing single-selection profiles and saved image signatures. Saving preserves the active choice if it remains selected; older payloads are accepted as a one-item list. Choosing multiple photos does not generate a batch. The daily “Another selected look” action cycles through the selected references and reuses the cache when available. A failed enqueue restores the previous choice. User avatars, imported looks, location and original photos are not migrated or overwritten by expanding the catalog.
