/**
 * frontend/app.js — SFI Single-Page Application Logic
 * =====================================================
 * Pure vanilla JavaScript (no frameworks). All state is in memory.
 *
 * CONFIG — replace these before opening in a browser:
 *   const API_URL      = "https://<api-id>.execute-api.us-east-1.amazonaws.com/dev";
 *   const WS_URL       = "wss://<ws-id>.execute-api.us-east-1.amazonaws.com/dev";
 *   const COGNITO_URL  = "https://<domain>.auth.us-east-1.amazoncognito.com";
 *   const CLIENT_ID    = "<your-cognito-client-id>";
 *   const REDIRECT_URI = window.location.origin + "/callback";
 *
 * After first deploy, get these values from CloudFormation / CDK stack outputs
 * and hardcode them here (or serve them from a /config endpoint).
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * WHAT TO BUILD — implement each section below
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * SECTION 1 — Auth / PKCE flow
 *   initAuth():
 *     - Check if URL contains ?code=... (OAuth callback)
 *     - If yes: exchange code for tokens (POST to Cognito /oauth2/token)
 *              store access_token + id_token in memory (NOT localStorage)
 *              remove ?code from URL (history.replaceState)
 *              call showApp()
 *     - If no: check if tokens already in memory → showApp()
 *              else → show auth screen
 *
 *   signIn():
 *     - Build Cognito Hosted UI URL with PKCE:
 *         Generate code_verifier (random 43-128 chars)
 *         Derive code_challenge = base64url(sha256(code_verifier))
 *         Store code_verifier in sessionStorage
 *     - Redirect: window.location = cognitoLoginUrl
 *
 *   signOut():
 *     - Clear in-memory tokens
 *     - Redirect to Cognito /logout?client_id=...&logout_uri=...
 *
 *   getAccessToken() → string | null
 *     - Return the in-memory access token (used in Authorization header)
 *     - Return null if not authenticated
 *
 * SECTION 2 — API calls
 *   apiRequest(method, path, body = null) → Promise<any>
 *     - Fetch from API_URL + path
 *     - Headers: {"Authorization": "Bearer " + getAccessToken(), "Content-Type": "application/json"}
 *     - On non-2xx: throw error with response body's "message" field
 *
 *   loadFiles(lastKey = null):
 *     - GET /files?limit=20&lastKey=...
 *     - Render each file into the file list
 *     - Show/hide "Load More" based on lastKey in response
 *
 *   uploadFile(file):
 *     - POST /files/upload with {fileName, contentType, fileSize}
 *     - Get back {uploadUrl, fileId}
 *     - PUT the raw file bytes to uploadUrl using fetch (no auth header — it's pre-signed)
 *     - Show upload progress using XMLHttpRequest onprogress event
 *     - On complete: show toast "Upload complete, processing..."
 *     - Start polling getFile(fileId) every 3 seconds until status !== PENDING/PROCESSING
 *       (or: connect WebSocket and listen for status updates)
 *
 *   getFile(fileId) → Promise<file object>
 *     - GET /files/{fileId}
 *
 *   deleteFile(fileId):
 *     - DELETE /files/{fileId}
 *     - Remove the card from the UI
 *     - Show toast "File deleted"
 *
 * SECTION 3 — WebSocket (real-time status push)
 *   connectWebSocket():
 *     - new WebSocket(WS_URL + "?userId=" + getUserId())
 *     - onmessage: parse JSON → {fileId, status}
 *                  find the file card in the DOM and update its status badge
 *                  if status === "PROCESSED": show "View Results" button
 *                  if status === "FAILED": show error badge
 *     - onclose: reconnect after 3 seconds (exponential backoff up to 30s)
 *   WHY: WebSocket push means users see PROCESSED immediately without polling.
 *
 * SECTION 4 — UI rendering
 *   renderFileCard(file) → HTMLElement
 *     - Build a card div from the file object
 *     - Include: name, type icon (📄 or 🖼️), date, status badge, action buttons
 *
 *   showResults(file):
 *     - Open the results modal
 *     - Populate: metadata, summary, extracted text (collapsible), entities/labels
 *     - "Download Original" button: fetch GET /files/{id} to get downloadUrl,
 *       then open it in a new tab
 *
 *   showToast(message, type = "info"):
 *     - Create a toast element, append to #toast-container
 *     - Auto-remove after 4 seconds
 *
 *   showApp():
 *     - Hide auth screen, show app screen
 *     - Display user email in header
 *     - loadFiles()
 *     - connectWebSocket()
 *
 * SECTION 5 — Event listeners (wire up on DOMContentLoaded)
 *   - Sign in / sign out buttons
 *   - Drop zone: dragover, dragleave, drop events
 *   - File input change
 *   - "Load More" button
 *   - Modal close button
 */

// TODO: implement all sections described above
