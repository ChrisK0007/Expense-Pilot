# Expense Pilot for iPhone — development build 0.1.1

This is an installable SwiftUI/WKWebView starter app for an iPhone running **iOS 17 or later**. It connects to your existing Expense Pilot **v0.8.1 or later** server. No paid Apple membership, package manager, third-party libraries or server update is required.

The first build deliberately reuses the working Expense Pilot web screens inside an iPhone app. Login, invitations, mandatory password changes, authenticator 2FA, split allocations, feature settings, receipts and reports remain governed by the server. It adds a native document scanner and the iOS share sheet for downloaded files. It is not yet a fully native rewrite of every screen.

## Install on your iPhone with your free Apple Account

1. On a **Mac**, install Xcode from the Mac App Store. Use an Xcode version that supports the iOS version on your phone. Open it once and allow its platform components to install.
2. Download this repository with **Code → Download ZIP** from https://github.com/ChrisK0007/Expense-Pilot, or clone it. Unzip it on your Mac.
3. Open **ios/ExpensePilot.xcodeproj** in Xcode. No project generation step is needed.
4. In **Xcode → Settings → Apple Accounts**, add your existing Apple Account. Accept any free developer agreement Apple presents; paid enrolment is not required.
5. In the project navigator, select **ExpensePilot**, then its **ExpensePilot app target → Signing & Capabilities**. Keep **Automatically manage signing** enabled. Choose your **Personal Team**.
6. If Xcode says the bundle identifier is unavailable, change `com.chrisk0007.ExpensePilot.dev` to a unique identifier such as `com.yourname.ExpensePilot.dev`. Keep that identifier for future updates.
7. Connect the iPhone to the Mac with a cable. Unlock it and accept **Trust This Computer**. Select your iPhone as the run destination beside the ExpensePilot scheme.
8. If requested, enable **Settings → Privacy & Security → Developer Mode** on the iPhone, restart it, then confirm. Developer Mode may only appear after pairing with Xcode. If iOS requests trust for your development certificate, follow its prompt under **Settings → General → VPN & Device Management**.
9. Press **Run ▶** in Xcode. It builds, signs, installs and opens Expense Pilot. Apple may ask you to sign in or approve device provisioning.
10. Tap **Connect to server** and enter your Expense Pilot address, then sign in with your existing app account. Your Apple Account is only used for signing, not your Expense Pilot login.

### Server address

- Away from home: use your existing **HTTPS** address, e.g. `https://expenses.example.com`. A reachable VPN address is another option.
- On the same trusted Wi-Fi as Unraid: use `http://YOUR-UNRAID-IP:8788` and explicitly enable **Allow HTTP on my local network**. For example, if your server is at 192.168.3.25, use `http://192.168.3.25:8788`. The server must permit HTTP cookies for this mode; a deployment with `COOKIE_SECURE=true` should use HTTPS.
- Enter the base address only, without `/api`, a login path or a subfolder.
- Public HTTP addresses, embedded credentials and invalid certificates are not accepted. HTTPS uses normal iOS certificate validation.
- Reverse proxies that redirect to a separate SSO/access-login domain are not supported by this first build. Use a direct Expense Pilot endpoint with its own authentication, or your existing VPN. Do not remove access protections just to make this build work.

## Using the app

- Existing screens and permissions match your browser workspace. Web sessions are kept by WebKit; the native code does not save your password. Sign-out in Expense Pilot works normally.
- Sign in and load the workspace while connected first. Tap the **scanner** in the top-right; it can open even if the connection has since dropped. Allow camera access, scan 1–8 pages, adjust the crop and tap Save. The PDF uploads to your receipt inbox for review. AI extraction is a separate action in the inbox.
- If the server is unreachable, the scanned PDF stays ready to upload. Keep the app open, reconnect and use **Retry upload**. Reload the workspace if needed, then retry. A pending scan is held only in memory: it can be lost if iOS terminates the app, you discard it or you disconnect/change servers. Every upload checks the live session, completed 2FA, current receipt permissions and the account that started the scan. A cold launch without a loaded, signed-in workspace still requires a connection first.
- The workspace’s normal receipt upload buttons can also choose existing photos or files.
- CSV/PDF downloads open the iPhone share sheet. Save to Files, AirDrop or choose another destination. Temporary exports are cleared on next launch or disconnect.
- **Gear → Disconnect & clear this device** clears the saved server, local web session and pending scan. It does not delete server records.

## Renewing the free installation

Apple’s Personal Team provisioning profiles expire after **7 days**. Connect the iPhone and press **Run** in Xcode again. Keep the same Apple Account and bundle identifier; do not delete the app just to renew it. You can continue developing without paying. TestFlight and App Store distribution require paid membership later.

## Included and not yet included

Included: existing expense workflows, native scanning, file sharing, configurable server, persistent web sign-in, loading/retry states and server-origin restrictions. No subscription, push-notification, iCloud or CarPlay entitlement is enabled.

Not yet included: background GPS trips, automatic CarPlay/Bluetooth detection, persistent offline queues/background synchronisation, Face ID app lock, share extensions, or native replacements for every web screen. Those are separate development stages; this build does not record location.

## Validation

The GitHub **Build iPhone development app** workflow compiles for the iOS simulator on a Mac runner, checks URL/origin validation and the receipt bridge (offline capture, retry, account changes, permissions and failed uploads), installs and launches the app, and saves a startup screenshot. Simulator checks do not validate camera hardware, free-account signing, your server’s network/certificate configuration or an end-to-end receipt upload from a physical iPhone. Those checks happen on your device after installation.

Manual first-run checklist:

- Sign in, complete 2FA, then sign out and back in.
- Upload a test receipt through the scanner, confirm its page count and check it appears in the server inbox.
- Create a small test expense, confirm its split allocation in the browser, then remove the test record.
- Export a report and save it to Files.
- With the signed-in workspace loaded, disable Wi-Fi **and mobile data** (or use Airplane Mode with Wi-Fi off). Tap the native scanner: it should open without a JavaScript error. Save a scan and confirm it stays waiting to upload. Keep the app open, reconnect, then tap **Retry upload** and check the inbox. Turning off Wi-Fi alone may leave a working mobile-data connection.
- If a retry requires sign-in, complete sign-in and 2FA using the original account, then retry. Switching to another account must not upload that pending scan.
- Check that a read-only tax agent cannot scan or upload; an agent with Read & write can. Employee accounts were removed in server 0.8.1 and must not be able to sign in.

Apple references:
- https://developer.apple.com/support/compare-memberships/
- https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices
- https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device

### Xcode 16.4 simulator troubleshooting

Apple documented a missing WebKit library in the iOS 18.5 simulator when targeting older iOS versions. If that simulator closes the app immediately with `libswiftWebKit.dylib` missing, use a newer Xcode/runtime or Apple’s workaround: https://developer.apple.com/forums/thread/785964. CI uses a simulator-only iOS 18.4 deployment override to avoid that runtime bug. The project’s physical-iPhone deployment target remains iOS 17.

## Update from iPhone build 0.1.0

Pull or download the current repository, open `ios/ExpensePilot.xcodeproj`, select your existing Personal Team and keep the **same bundle identifier** you used for the installed app. Select your phone and press **Run** again. Do not delete the installed app. Settings shows iPhone app **0.1.1**. This is an iPhone app fix; server 0.8.2 and your Docker configuration stay the same.

The Scan button previously requested `/api/session` before opening the camera. Without a connection, that rejected JavaScript promise surfaced as a generic exception. Camera startup now uses the loaded workspace's account state without a network request; server authentication and permissions are freshly checked before any PDF is uploaded. Capture works after connectivity is lost, but it does not provide a persistent offline queue or offline expense editing.
