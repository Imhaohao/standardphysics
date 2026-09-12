# A to D: the iOS WebView needs a session handoff contract

Lane A has the allowlisted `WKWebView` and its single `scanShop` native action. The repository has no login flow, session endpoint, cookie contract, or authenticated web app yet, so the shell cannot establish an authenticated session safely.

Please define the server endpoint that exchanges an authenticated native sign-in for a short-lived, single-use web session. The response should let iOS install a host-scoped `HttpOnly`, `Secure` session cookie before loading the workspace URL. Please also define the expired-session response so the app can return to sign-in. The native app will keep provider keys and upload credentials out of the WebView.

Once the endpoint and web host exist, Lane A will add the sign-in step, perform the exchange, install the cookie in `WKHTTPCookieStore`, and load the workspace only after the cookie write completes.
