# Weather-first photographic wardrobe (local pilot)

## Delivered screens

Today, 24-hour and seven-day Forecast, Rain & radar, saved Looks, outfit Detail, Change a piece, garment-photo Upload, and Location/preferences. The live weather uses Open-Meteo current/hourly/daily/minutely data; air quality is a separate Open-Meteo/CAMS request. RainViewer provides recent observed radar frames over attributed OpenStreetMap tiles. Radar is historical, not predictive; the rain chart is a 15-minute model forecast, not minute-by-minute nowcasting. Errors and missing values remain visible rather than becoming sample numbers. Weather is cached for ten minutes, air quality for thirty minutes, and map tiles for ten minutes.

Your approved avatar and the three existing saved outfits are byte-identical to the prior library. Existing outfit detail cards are photographic crops from the saved render, labeled “As worn”; they are not claimed to be retailer product photos. A real UNIQLO Twill Overshirt product photograph was imported privately for testing, with its source link. New user uploads are normalized, stripped of EXIF, stored per owner, and never sent to the weather providers.

New try-ons send the actual product photo and selected saved look to FASHN `tryon-max`, 2K balanced, one image. Results remain unapproved previews until Save as new look. They retain garment IDs and their source look, leaving the approved base and prior outfits untouched. Caching, credit reservations, ownership checks, CSRF, restart polling and uncertain-submission safeguards are shared with the existing provider adapter. The live garment test consumed 3 credits and remains an unapproved preview.

The Today screen uses the exact matching saved weather category first. If missing, it shows a clearly labeled closest saved look and explains that a different/warmer layer is needed, with a separate priced generation action. Automatic generation remains opt-in. The recommendations cover the next six hours, not just the current temperature.

## Scope and limitations

This is still a localhost Flask pilot inside a UIKit/WKWebView simulator shell. Keep the Mac server running. It is not a deployed native iOS service. No retailer catalog sync, stock/prices, exact fit guarantee, official severe-weather alert feed, or commercial asset license is implied. Only the manually sourced test garment and user-uploaded photographs are in the real garment library. Retailer photo reuse needs appropriate permission before distribution. Open-Meteo free service and public radar access must be reviewed for production/commercial requirements.

## Sources

- Weather: https://open-meteo.com/en/docs
- Air quality: https://open-meteo.com/en/docs/air-quality-api
- Radar: https://www.rainviewer.com/api/weather-maps-api.html
- Map attribution: https://www.openstreetmap.org/copyright
- Photo-based try-on: https://docs.fashn.ai/api-reference/tryon-max
- Test garment: https://www.uniqlo.com/uk/en/products/E476008-000/00?colorDisplayCode=56

## Verification

42 backend tests passed, including new garment privacy/CSRF, duplicate try-on suppression, explicit acceptance and base preservation, deletion, full weather value mapping, and opaque radar frame IDs. Live NYC returned 24 hourly points, seven days, eight rain intervals, air quality, and a composed radar map. One real image-based try-on completed and was retained for user review. iOS Simulator checks cover Today, Forecast, Rain and the photographic wardrobe.


## Approved concept visual alignment

The live UI now uses the earlier photographic design board as its visual reference: a locally bundled generated sky backdrop, compact Today hierarchy with the full saved avatar above navigation, translucent forecast cards, outline navigation/weather icons, and a two-column photographic wardrobe. Forecast defaults to the compact overview; Details reveals the full hourly strip and extra weather readings. The iOS shell extends the sky under the status bar and applies safe-area padding in the web layout.

Live weather values and the user's actual saved wardrobe replace the illustrative values and extra outfits in the concept. Existing looks without original product photographs use labeled photographic crops from the saved image. They are not misrepresented as retailer product cutouts. The imported UNIQLO source photograph remains available for image-based try-on. The redesign does not regenerate or overwrite any avatar or look.


## Condition-specific backgrounds

Eight generated photographic assets in `static/images/weather/` join the existing partly-cloudy sky. `weather-scene.mjs` maps current WMO codes to clear, partly cloudy, overcast, rain/drizzle/freezing rain, snow, fog, or storm. Clear and cloudy nights have separate images; precipitation and fog get darker nighttime overlays. Unknown codes use a neutral fallback. Current `is_day` comes from the weather provider for the selected location; upcoming rain and clothing recommendations do not control the background. Wardrobe screens retain their neutral surface.

No image generation happens on refresh or navigation. The local preview gallery at `/static/weather-backgrounds.html` labels all conditions as illustrative and uses the same selection function and CSS. The exact generation prompts are recorded in `weather-background-prompts.json`.

Validation: 42 Python tests, three Node test groups covering every supported WMO code, nighttime selection, and unknown values. Visually inspected all scenes in the gallery and the actual clear-night scene selected by NYC live data in the iOS simulator.
