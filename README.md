# WeatherAvatar

A local weather app with a personalized photographic avatar, a visual wardrobe, live forecasts, and saved weather-appropriate outfits.

## Current app

- Selfie upload, avatar approval, and separate saved avatar profiles.
- Photographic wardrobe references, multiple looks per weather category, and full live weather information.
- FASHN Try-On Max generation with automatic OpenAI clothing/appearance checks and at most two targeted repairs.
- Accepted outfit images cached by avatar and reference, reused across weather changes without regenerating.
- Local SQLite storage, credit accounting, private image routes, and a development iOS Simulator shell.

## Run the current app

```sh
uv sync
uv run python pilot.py
```

Open http://127.0.0.1:5076/pilot. Configure `FASHN_API_KEY` through your secret manager for generation. To enable automatic checks, also provide `OPENAI_API_KEY` and set `OPENAI_OUTFIT_REVIEW_ENABLED=1`; this sends the approved avatar, clothing reference, and candidate image to OpenAI. Without review access, results remain previews for manual approval. No API credentials are included in this repository.

`scripts/run-pilot.sh` is the original developer's local Keychain launcher; other environments can run `pilot.py` with their own secret-manager environment. `ios-simulator/README.md` documents the development preview.

Personal photographs, avatars, generated results, databases, and private benchmark inputs are intentionally excluded. They remain in the original local app. This is a localhost pilot, not an internet-ready deployment.

## Checks

```sh
uv run python -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
```

See [the repair pipeline](docs/max-repair-pipeline.md), [onboarding](docs/avatar-onboarding.md), and [weather experience](docs/weather-v2.md).

---

## Earlier prototype documentation


A Flask app that turns the weather into a daily outfit, illustrated on a customizable full-body avatar.

## Daily outfit experience

Open `/today` (also the destination of `/` and `/outfit`). No account or API key is needed to try it.

- Full-body vector avatar with facial features, four hair styles, five skin tones, four hair colors, three builds, and adjustable height.
- Layered tees, button-downs, knits, overshirts, rain shells, insulated coats, shorts/trousers, sneakers/boots. Four coordinated color palettes.
- Recommendations use hourly **apparent temperature**, rain probability/conditions, wind, personal warmth preference, and activity. Apparent temperature already includes environmental effects; wind is not subtracted a second time.
- Choose the next twelve forecast hours or remaining morning/afternoon/evening hours. Elapsed periods are disabled. Weather uses the selected location's timezone.
- Search and select a city, or explicitly request browser geolocation. Forecasts are returned directly for those coordinates, never read from another user's weather history.
- Four clearly labeled sample forecasts support exploration without network access. Live forecast failures remain explicit rather than silently substituting sample data.
- Avatar appearance is saved in this browser's local storage. Canceling the editor restores the previous appearance. The last selected location, comfort, activity, units, and palette are also saved locally; a returning visit refreshes the last location. Nothing is synced to an account.

This first iteration uses generic illustrated clothing. The daily view does **not** implement a personal wardrobe, retailer catalogues, virtual try-on, or garment fit prediction. A separate local selfie pilot is described below. The original account/profile pages remain available but are not required for the new experience; their saved profiles do not sync with the browser avatar yet.

## Run locally

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync
# Use an isolated development database rather than the legacy tracked database.
DATABASE_URL=sqlite:////tmp/weatheravatar-dev.db uv run flask --app main run --port 5074
```

Open http://127.0.0.1:5074/today. Sample mode works immediately. Internet access is needed for live weather and optional Google Fonts; system font fallbacks are provided.

Set `SESSION_SECRET` for any shared environment. Debug is off by default; set `FLASK_DEBUG=1` only for local development. For a deployed service, use Gunicorn, not Flask's development server.

## Weather sources and endpoints

New daily experience:

- `GET /api/locations?q=Caracas`: Open-Meteo geocoding, up to five results for explicit location selection.
- `GET /api/daily-weather?lat=10.5&lon=-66.9`: Open-Meteo current weather and two days of hourly forecasts. Celsius, km/h, and the location's local time.

Weather attribution: [Open-Meteo](https://open-meteo.com/). The public endpoints are for noncommercial use; review [their pricing and usage terms](https://open-meteo.com/en/pricing) before a commercial release. Production hardening should add rate limits and caching keyed by coordinates. The endpoint currently makes a request per explicit location selection.

Legacy weather endpoints still use `OPENWEATHER_API_KEY`. They are not used by the new daily view.

## Validate

```sh
uv run python -m unittest discover -s tests -v
node --test tests/outfit-engine.test.mjs
```

Tests cover forecast input validation, provider failures, location isolation, cold/rain/heat/wind behavior, comfort and activity adjustments, and forecast windows crossing midnight.

## Main files

- `daily.py`: daily view and weather adapter.
- `templates/daily.html`, `static/css/daily.css`: responsive daily interface.
- `static/js/outfit-engine.mjs`: deterministic outfit selection and forecast windows.
- `static/js/avatar.mjs`: vector avatar and garment layers.
- `static/js/daily.mjs`: UI, location selection, and local appearance preferences.

Next: user-owned garments and persistence, then optional selfie likeness. Keep outfit selection separate from rendering so both can evolve independently.


## Persistent avatar feasibility pilot (v2)

Run `python pilot.py` with `OPENAI_API_KEY` injected by your credential manager (never put credentials in source). Open http://127.0.0.1:5076/pilot. `PILOT_PORT` can override the port. The previous in-memory pilot on 5075 can remain running while you export its results; it is not automatically migrated.

### Workflow

1. Upload your own adult selfie. Optionally describe body/build and presentation corrections. The separate Reference quality selector controls the full-body reference candidate; outfit comparison quality checkboxes do not block reference creation.
2. Review the generated reference. Fit the protected ellipse around the face and hair, keeping clothing outside. Approve it explicitly to create Avatar v1. Further candidates do not replace it until approved as a new version; previous versions remain selectable.
3. Compare direct selfie generation, approved-avatar edits, and edits with head protection. Compare all three at one quality, or one method at three qualities. Maximum three new images per comparison.
4. Rate likeness, body consistency, framing, clothing-brief fidelity, overall outfit quality, and the head/neck join separately. Mark whether you would use each portrait. Export JSON with usage, latency, prompts, immutable identity versions, outfit specifications and ratings; download images separately.
5. Request the same outfit again to reuse saved results without a new API call. Mark an output rejected before requesting another attempt. Unreviewed cached images can be inspected again, but do not count as accepted results.

These are fixed-pose 2D portraits, not a rigged 3D avatar or garment fit prediction. A selfie does not establish body measurements. One input photo is retained per local library; changed-reference/haircut onboarding and optional full-body reference uploads are still future work. Body preferences can produce a new approved version from the same selfie.

### Identity protection and cache

`avatar_pipeline.py` separates generic wardrobe items, versioned outfit selections, pose, renderer version and identity references. Cache keys include avatar ID, garment specifications/versions and layer order, pose, method and quality. They exclude exact temperature, location and timestamps. Garment attributes are suggestions, not verified material or performance claims; no retailer inventory or product-image fidelity is tested here.

OpenAI supplies the baseline renderer. Protected edits send a PNG mask whose opaque ellipse protects the head. Because the provider may not obey a mask exactly, local compositing restores the approved pixels inside that ellipse with a small feather outside it. Actual output dimensions and core pixel equality are checked. Body alignment, silhouette, framing and boundary blending are **human checks**, not automated identity recognition or pose validation. Outside the protected ellipse, consistency is not guaranteed. The background is requested in the prompt, not separately segmented or composited. The renderer is injectable for tests and future provider adapters.

Sources: [OpenAI image editing and limitations](https://developers.openai.com/api/docs/guides/image-generation), [pricing](https://developers.openai.com/api/docs/models/gpt-image-1.5).

### Local persistence and privacy

`pilot_store.py` stores private photos, approved references, images, ratings, queue states and request IDs in `instance/avatar-pilot/pilot.sqlite3`, ignored by Git. The directory is created with mode 0700 and database mode 0600. This is filesystem protection, **not application-level encryption**; protect the host and backups accordingly. The database also retains the signing secret for browser session continuity, but never stores the OpenAI key. Access remains scoped to the owning browser's cookie (31-day session). Losing that cookie can make its library inaccessible; cross-device/account recovery is not implemented.

The local UI provides explicit deletion of its photo, versions, results and ratings. SQLite secure deletion is enabled; filesystem snapshots/backups and provider retention are outside that deletion. Photos are validated, oriented and re-encoded without EXIF metadata before sending. No-store responses, CSRF validation, trusted hosts, and loopback-only requests protect the local endpoint. Run as one local process only; this is not a public service.

### Jobs and cost accounting

One worker handles durable job records. Every queued request is persisted before dispatch. A restart marks unfinished jobs interrupted and does not retry them automatically, because billing may already have occurred. Duplicate request IDs return the original jobs; equivalent outfit requests reuse matching queued or completed jobs. Provider failures are not automatically retried. Rejected completed outputs are excluded from reuse.

The pilot has a **persistent 24-image allowance**, including reference candidates. Clearing a library or restarting does not reset it. This is an image-count guard, not a dollar budget. Existing renders remain viewable without a configured API key. Previews show approximate output cost; input costs are additional.

Pricing verified 2026-10-29: portrait output estimates $0.013 / $0.050 / $0.200 for low/medium/high. Post-generation estimates apply standard undiscounted rates to reported usage: text input $5/M, image input $8/M, image output $32/M. Cached-input discounts are not subtracted. Missing usage remains unknown. Failed requests can still have charges; unknown costs are flagged rather than treated as free. Cost per keeper includes all known attempts for that method; shared onboarding is shown separately. No invoice or account-balance claims are made.

### Evaluation and remaining work

Automated tests cover persistence, cache reuse/invalidation, immutable approval versions, comparison branches, head-mask alpha semantics, exact protected pixels, dimension mismatch, rejected-result retry, interrupted-job recovery, private session access, CSRF, consent, malformed inputs, cost estimation, ratings, exports and deletion. Provider calls are mocked for these tests; a prior live read-only model-access check succeeded. Real generation quality, mask behavior at the provider, acceptance rates, latency and costs still need consenting participant trials.

Release target: at least 90% first-attempt acceptance with stable framing and no recurring body/identity drift across diverse consenting adults. This is an unvalidated target. The UI distinguishes accepted/rated results from first-attempt acceptance across distinct looks. No production-readiness claim follows from one person's successful selfie.

Before public deployment: authenticated accounts and recovery, encrypted private object storage with expiry, durable external workers, per-user budgets and provider reconciliation, automatic alignment/segmentation evaluation, actual garment references, and a broader participant study. The daily weather screen is still separate: this pilot uses controlled scenarios to isolate rendering quality. No forecast prefetch or live weather-triggered generation is implemented.


## Permanent-avatar experience (v3)

`/pilot` now opens the everyday wardrobe view. Ratings and method comparisons remain available only at `/evaluate`; prior ratings and portraits are preserved. The existing local photo was used to create a single high-quality base, pinned by `permanent_avatar`. Outfit requests never promote an outfit image to the base or require another selfie. The main UI shows the base while a missing look renders, and reuses matching saved looks immediately.

`POST /api/pilot/dress` selects the pinned identity and medium quality server-side. It accepts only the weather scenario, consent and request ID. The face/frame cannot be switched by that endpoint. A calibrated, versioned set of per-weather clothing polygons is stored on the identity, including protected neck, hand, and (for short sleeves) forearm regions. A provider edit mask restricts the request; deterministic compositing then inserts only pixels within the clothing envelope, with inward feathering. Every pixel outside that envelope is checked against the original base. Dimension mismatch or protected-pixel differences reject the output. Tests verify these invariants with entirely different source and generated frames.

This initial geometry is calibrated for this user's one permanent base. Other identities must be calibrated before the dress endpoint is enabled; arbitrary auto-generated references do not silently receive these polygons. Region changes should create a new identity/region version and cache key. The background within the allowed garment silhouette may change, and clothing seams or fit inside the editable region are not guaranteed. Pose and face outside that region remain original pixels; this is not full-body segmentation or a virtual-fit model. Warm-weather trousers replace shorts so no unseen bare legs need to be invented. A newly generated base's likeness still needs the user's visual judgment.

New looks explicitly send the saved base to OpenAI when requested. The existing key remains injected through the credential broker; no credentials or private image files are committed. The current real-photo smoke test creates the base and two outfit examples, with measured token estimates saved alongside the jobs.


### Garment edge correction

Clothing polygons describe the old garments, not a safe cut line for new garments.
The clothing pipeline now supports a bounded `edge_margin_px` (0–64) and
`edge_feather_px` (1–24). It expands the clothing envelope first, then subtracts
protected skin regions. The outer transition is eroded and feathered inward so
fabric edges have room to finish before blending into the original background.
The current personal calibration uses a 32-pixel margin and 12-pixel transition
on the 1024×1536 canvas. This permits a narrow background margin to change; the
protected face/hands and pixels outside the envelope remain exact. Prompting now
requests an in-place photographic retouch with fixed joint positions.

Pixel invariance is not a visual quality score. Model drift can still produce
halos or doubled hands, so replacement looks require visual inspection before
acceptance. No automatic paid retries are performed.


The two repaired saved looks additionally use individually reviewed garment
mattes and vertical landmark alignment. `compose_clothes(..., garment_matte=...)`
accepts that matte but always intersects it with the protected envelope. This
removes the model's repainted background rather than fading it into the source.
Raw renders, aligned layers and calibration masks stay under the ignored private
`instance/avatar-pilot/edge-calibration` directory. The current online generation
path does **not** automatically segment and align arbitrary new outfits; these
saved-look repairs are manually calibrated, not proof of general segmentation.
