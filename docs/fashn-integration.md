# FASHN integration plan

Status: FASHN API connected through macOS Keychain. Approved Studio base and sunny outfit imported at original resolution. Live API rain generation validated at 3 credits. Live weather, wardrobe preferences, and onboarding are implemented; this remains a local, single-user pilot.

## Local operation

Run `pilot.py` with `FASHN_API_KEY` injected by the credential broker (never in a browser or committed file). The existing SQLite database now also holds `fashn_jobs` and `fashn_avatars`. Main experience uses `/api/fashn`; `/evaluate` retains the legacy OpenAI experiment. Existing photos are reused; legacy generated images are not relabeled as FASHN outputs.

Pilot limits are 12 credits per local session and 24 globally, including reserved/uncertain spend. These are cumulative safety ceilings, not provider balance checks or a subscription allowance. Unknown submissions remain blocked for manual provider reconciliation. Failed/expired cached requests do not automatically retry; replacement/reconciliation UI is follow-up work. Deleting a library clears images but keeps a minimal cost ledger. Single process only; do not run multiple Flask workers.

The main screen accepts an approved imported Studio base or an API-generated base. The accepted Studio full-resolution base is imported and approved. Provider GET failures keep polling with a visible waiting message; no POST retry is issued. Full-body composition still requires the one-time human approval; output dimensions are validated without stretching.

## Product flow

Use FASHN Edit first, matching the Studio workflow accepted by the user: selfie -> full-body reference -> independent outfit edits from that reference. A one-time “Use this avatar” action pins the reference version. Daily forecasts select a saved outfit; they do not regenerate the person. No ratings in the main experience. Preserve the existing pilot library and mark the old composite renderer as legacy.

The approved Studio reference and sunny output are imported at their original 1536 × 2752 resolution, with Studio provenance and no fabricated API prediction IDs. New users create and approve one base portrait. Rejected candidates remain in the private history and can be replaced explicitly.

## Backend changes

- Add a FASHN adapter with separate submit, poll, and retrieve operations. Keep FASHN_API_KEY server-side, locally in the credential broker and in a hosted secret manager after deployment.
- Submit POST https://api.fashn.ai/v1/run with model_name=edit. Inputs: image (private base64 data URI), prompt, resolution=2k, generation_mode=balanced, num_images=1, output_format=png, return_base64=true. Never log image data or authorization headers.
- Store the prediction ID immediately. Poll GET /v1/status/{id}. A job can be starting, in_queue, processing, completed, or failed.
- Persist states independently of process memory. On restart, resume polling known IDs instead of marking everything interrupted or submitting again. A submission timeout without an ID is an unknown outcome; do not automatically resubmit it.
- Store output bytes in our private asset store immediately, then mark the job complete. Base64 results expire after 60 minutes. Provider CDN links are not permanent storage.
- Record provider, model name, settings, prompt version, source avatar version, provider prediction ID, actual image dimensions, and x-fashn-credits-used. Count billed credits once per prediction; poll responses must not increment spend repeatedly.
- Remove OpenAI-specific authorization gates, token-price calculations, fixed 1024x1536 validation, and compose_clothes/preserve_head from the FASHN path. Keep image decoding, size limits, session ownership, CSRF, and request validation.
- Validate aspect ratio and full-body composition without stretching images. UI must stop claiming pixel-identical face/frame preservation for this generative renderer.

## Caching and budget controls

Unique cache identity: user + immutable avatar version + outfit specification version + provider/model + render settings + prompt version. Persist a unique reservation so simultaneous requests for one look share a job. Do not use temperature, location, date, or weather refresh timestamp as cache keys.

Reserve predicted credits before enqueue, enforce per-user and global spend caps transactionally, settle with actual billed credits, and release reservations on confirmed failure. Keep uncertain submissions reserved pending reconciliation. The existing persistent 24-image counter is not a dollar budget.

At published on-demand pricing, Edit 2K balanced consumes 3 credits = $0.225 per output. One base plus two outfits is approximately $0.675 before rejected results. The Studio free-credit debits observed in the test are not API prices. API credits are purchased separately; a developer key requires API credit purchase, with a published $7.50 minimum.

## Scale and reliability

Local pilot: SQLite persisted jobs and a small worker, with polling independent of incoming HTTP requests. Hosted service: durable queue, Postgres job/budget records, private object storage, authenticated users, and rate-limited workers. The documented default is six concurrent provider requests; request increased capacity before broad launch. Use webhooks once a public backend is available, after verifying the provider's authentication/delivery contract. Polling is sufficient locally.

Keep the last successful look visible during generation. Generation errors must leave saved looks accessible. No automatic paid retries for aesthetically rejected images. Explicit replacement creates a new reference version, invalidating matching outfits without deleting history. Deletion during an active job must prevent the worker from restoring deleted assets.

## Validation before rollout

Mocked tests: request contract; no key/image leakage; duplicate suppression; restart recovery with prediction ID; unknown submit outcome; actual-credit accounting exactly once; budget reservations; output decoding and expiry handling; ownership; deletion during generation; cache invalidation; no legacy compositing.

Live smoke test after API access: one base and two independent outfits, capped at nine expected credits. Compare with accepted Studio examples. The Edit endpoint is experimental: watch for provider changes and preserve a configurable adapter. This flow offers visual consistency, not a mathematically fixed 3D body.

## Later wardrobe integration

When garment photos exist, benchmark tryon-max separately using model_image=approved base and product_image=garment. The current evidence supports prompt-based Edit only. Do not promise exact brand garments until this test succeeds.

## Sources

- https://docs.fashn.ai/api-reference/edit
- https://docs.fashn.ai/api-overview/api-fundamentals
- https://docs.fashn.ai/api-overview/data-retention-privacy
- https://docs.fashn.ai/getting-started/api-setup
- https://help.fashn.ai/plans-and-pricing/api-pricing

## Local network repair (2026-11-02)

ExpressVPN configured macOS DNS as `100.64.100.1`; UDP lookups timed out and TCP lookup closed without an answer. The browser could load FASHN while Python could not resolve `api.fashn.ai`. An encrypted DNS query returned valid public addresses; an authenticated API balance check then returned HTTP 200 with 100 credits.

Use `scripts/run-pilot.sh` on this Mac. It injects only FASHN_API_KEY through Keychain and enables FASHN_DNS_MODE=encrypted. This resolves allowlisted provider hosts through Cloudflare DNS over HTTPS, caches the answer within its TTL, and preserves the original Host header, TLS SNI, certificate verification and hostname assertion. No system DNS/VPN settings are modified. The credential and photo never go to the DNS resolver. POST retries remain disabled.

The initial unknown rain request was reconciled against an empty provider request history and unchanged 100-credit balance, then explicitly requeued once after connectivity was verified. Imported Studio base and sun assets remain unchanged.


## Live weather and daily experience

Open-Meteo current conditions and the next six hourly forecasts select among warm/dry, cool/breezy, rain, warm rain, cold/dry, and cold rain/snow. Apparent temperature, precipitation probability/amount and wind drive deterministic selection. Forecasts are cached for ten minutes; a failed request shows an error instead of inventing weather. City search and optional browser geolocation are available. Coordinates are rounded to two decimals before local storage and forecast requests.

New-user flow: introduction → photo/selfie → portrait generation → approve or reject → generic wardrobe choices and city → daily forecast. Returning approved users skip onboarding. Choices and city persist in `weather_profiles` in the private SQLite database. The existing user starts with NYC and the defaults matching previously saved outfits.

Saved looks match avatar version, weather category and wardrobe choices. Weather refreshes and dates never invalidate an outfit. Changed clothing choices require a corresponding new look. Automatic generation is opt-in and uses the existing cumulative pilot credit caps; otherwise the daily view offers a priced create button. Unknown or failed jobs never automatically resubmit. There are no ratings in the daily experience.

The wardrobe is a curated textual selection, not real retailer inventory or exact garment try-on. FASHN Edit can vary facial/body details. Open-Meteo's free service is for this noncommercial pilot; select the appropriate commercial plan before a production launch. Hosted launch also requires user authentication, private object storage, a durable worker queue, per-user budgets and database migration.

Weather references: https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/geocoding-api

Full-resolution base uploads can exceed ten seconds on this connection. Submission now allows a 60-second connection/upload timeout and a 90-second response timeout. Unknown outcomes still require provider-history reconciliation before retry; increasing the timeout never enables automatic POST retries.
