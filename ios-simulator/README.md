# iOS Simulator preview

This is a small UIKit/WKWebView development shell for the local Flask app, not a standalone native or App Store build. It uses the same approved avatar and SQLite library, without copying or regenerating images. The Mac server must remain running on `127.0.0.1:5076`.

1. Start `scripts/run-pilot.sh` (FASHN key stays in Keychain/server).
2. Run `ios-simulator/build.sh`.
3. Boot the iPhone 17 Pro iOS 26 simulator.
4. Run `.venv/bin/python ios-simulator/run.py`.

The launcher selects the sole approved local profile and passes its signed session privately to the child simulator app. No API key is embedded. The session persists in the app's WebKit cookie store. If more than one approved profile exists, the launcher stops rather than guessing. This local development convenience is not a production authentication system.

Production iOS packaging needs account sign-in, HTTPS hosted services, error/offline navigation, real-device camera/location testing and distribution signing. The current UI already supports safe-area insets and touch-friendly visual wardrobe choices.
