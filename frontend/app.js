// this will enable stricter javascript rules
// ex accidentally assigning a value to an undeclared variable causes an error
"use strict";

// these are all placeholders that will be filled correctly once resources deployed
// they are all designed to be public bc they are frontend code
// what shouldnt be inside frontend code is aws access keys, cognito app client secret, database passwords, bedrock api credentials, etc
const API_URL = "https://<api-id>.execute-api.us-east-1.amazonaws.com/dev";
const WS_URL = "wss://<ws-id>.execute-api.us-east-1.amazonaws.com/dev";
const COGNITO_URL = "https://<domain>.auth.us-east-1.amazoncognito.com";
const CLIENT_ID = "<your-cognito-client-id>";
const REDIRECT_URI = window.location.origin + "/callback";
const LOGOUT_URI = window.location.origin + "/";

// let creates a variable whose value can change later
// opposite of const whose can't be changed
let accessToken = null; // stores cognito access token after login
// remember cognito first returns a authorization code which is then exchanged for the tokens
// the token is what API verifies
// if someone steals your auth code they can't use because theres a verifying random string hash also sent by your browswer
// would be bad if attacker got the verifier too but obviosly worse case they get access token itself
let idToken = null;  // stores the cognito ID token which is info about user
let tokenExpiresAt = 0; // stores the time the login exprires
let socket = null;  // stores websocket connection
let reconnectTimer = null;  // if websocket disconnects timer ID gets saved here
let reconnectAttempt = 0;  // counts reconnect attempts for exponential backoff
let nextPageKey = null;  // stores dynamoDB pagination info
let loadingFiles = false;  // flag to prevent double clicking and two requests simulaneously
let appStarted = false; // has app been intialized so no two websockets event listeners etc
let sessionVersion = 0; // prevents previous login session from modifying the current session
// when the page is closed its 0 again so its not a security feature
// it protects again old async operations with the current page instance
// when you close the page the browswer closes the TCP/websocket connections so it doesn't get old async operations

// sotres file objects using their IDs as keys
const filesById = new Map();
// stores each files status check timer
const pollingTimers = new Map();
const pollingControllers = new Map();
// track active upload requests so they can be cancled when session ends
const activeUploads = new Set();

// helper function named $
// its common for java script programmers to use
// ...ids gathers all supplied agruments into an array
// HTML is what exists on the page
// JavaScript is code that manipulates the page
// broswer reads HTML builds the DOM document object model
// its a tree in memory so here the broswer looks inside its DOM tree
const $ = (...ids) => {
  for (const id of ids) {  // loops thru given IDs and sees if HTML currently loaded in page has an element with that ID
    const element = document.getElementById(id);
    if (element) return element;
  }
  return null;
};

// helper for creating HTML elements
// normally thr broswer parses the HTML and creates DOM elements automatically
// this only needed when JavaScript wnats to create new element dynamically after page has loaded
function createElement(tag, className, text) {
// creates the requested element
// adds CSS classes and text when given
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

// helper function for changing elements visibility
function setVisible(element, visible) {
  if (!element) return;
  element.hidden = !visible;
  element.style.display = visible ? "" : "none";
}

// function for converting bytes into URL safe Base64
function base64Url(bytes) {
  return btoa(String.fromCharCode(...bytes))
  // ... spreads bytes into 72, 101, 108, 108, 111 for example
  // then converts character codes to actual characters like 65 to "A"
  // these characters can be awkward for URL so change
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

// a cryptographically secure random string generator
function randomString() {
  return base64Url(crypto.getRandomValues(new Uint8Array(48)));
}

// defines a JWT payload decoder
// stands for json web token usually given by a server after you log in
// a package that contains information about a user
function decodeToken(token) {
  try {
    const segment = token.split(".")[1];
    const normalized = segment.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const bytes = Uint8Array.from(atob(padded), character => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return {};
  }
}

// reads congnitos sub claim from ID token or reads access token
// in cognito sub stands for subject its like users permanent unqiue ID
function getUserId() {
  return decodeToken(idToken).sub || decodeToken(accessToken).sub || null;
}

// helper used before authenticated operations
function getAccessToken() {
  if (!accessToken) return null; // returns null when isgned out
    // check whether token has expired
    // clears session then displays the sign in screen andnotifies the user
  if (Date.now() >= tokenExpiresAt) {
    clearSession();
    showAuthScreen();
    showToast("Your session expired. Please sign in again.", "error");
    return null;
  }
    // returns a valid token
  return accessToken;
}
// function to stop checking one file processing status
// websocket is the primary method but polling acts as a fallback when websocket is unavaliable
// when websocket reconnects this function stops the fallback
function stopPolling(fileId) {
    // when you do setTimeout() it returns a ID resprenting that scheduled future action
    // when ex 3 seconds pass broswer seeings job #17 is due
    // the broswer constantly checks has #17 time arrived and when it does it places the callback into the event loop
    // callback is the function gave to be called later
  const timer = pollingTimers.get(String(fileId));
  // cancels the scheduled status check if a timer exists
  if (timer) clearTimeout(timer);
  pollingTimers.delete(String(fileId)); // remove timers entry from map
  // when poll is started it creates an abortcontroller and stores in pollingControllers
  pollingControllers.get(String(fileId))?.abort(); // cancles polling requests already running
  pollingControllers.delete(String(fileId)); 
}

// decides if a websocket is connected its true when exists and state is OPEN
function isWebSocketAvailable() {
  return socket?.readyState === WebSocket.OPEN;
}

// function for stopping polling for every tracket file
// Array.from makes an array of all the keys
function stopAllPolling() {
  for (const fileId of Array.from(pollingTimers.keys())) stopPolling(fileId);
}

// exits immeediately if websocket connected and user doesn't have valid access token
function startFallbackPolling() {
  if (isWebSocketAvailable() || !getAccessToken()) return;

    // loop thru all cached file objects and start polling for files who status is PENDING or PROCESSING
  for (const file of filesById.values()) {
    if (isProcessing(file.processingStatus)) pollFileStatus(file.fileId);
  }
}

// async to a function allows the await keyword 
// await pauses pauses that specific function until the background task finishes without freezing the rest of the website 
// async always returns a Promise no matter whats returned its wrapped in a promise
// this function fetches the latest information for a processing file that may have been missed 
// called immediately after a websocket connection opens
// its purpose is to check if any processing files finished before socket connected
// so after websocket connects the function fetches files current information and discovers its status
async function refreshPendingFile(fileId, connection = socket) {
  const version = sessionVersion;
  // exits if file not in map and file is not pending or processing
  const snapshot = filesById.get(String(fileId));
  if (!snapshot || !isProcessing(snapshot.processingStatus)) return;

  try {
    // gets current file information
    const latest = await getFile(fileId);
  
    if (
      version !== sessionVersion ||   // makes sure user didnt change session
      socket !== connection || // make sure socket that triggered fetch is still current
      !isWebSocketAvailable() ||  // make sure websocket still avaliable
      filesById.get(String(fileId)) !== snapshot  // make sure file wasnt removed
    ) return;
    // these two lines take fetched information and notify user if has changed
    const updated = upsertFile({ ...latest, fileId: String(fileId) });
    if (updated) notifyStatus(updated, snapshot.processingStatus);
  } catch (error) {
    if (version === sessionVersion && socket === connection && isWebSocketAvailable()) {
      showToast(error.message || "Unable to refresh file status.", "error");
    }
  }
}

// called hwne signing out or when auth becomes invlaid
function clearSession() {
  sessionVersion += 1; // ups count so older work can recongize that its outdated
  // remove tokens
  accessToken = null;
  idToken = null;
  tokenExpiresAt = 0;
  appStarted = false;
  nextPageKey = null;
  reconnectAttempt = 0;

  // cancels a scheduled websocket reconnection
  // only effective if theres actually reconnect waiting to happen
  // entire app uses one websocket connection so theres only one reconnect timer
  clearTimeout(reconnectTimer);
  reconnectTimer = null;
    // checks if websocket exists 
  if (socket) {
    // remember handleris a function that runs automatically when event happens
    socket.onclose = null; // remove handler so doesnt reconnect
    socket.close();
    socket = null;
  }

  // clears polling timers and active polling requests
  stopAllPolling();
  // clears active file uploads by apporting http request
  for (const xhr of activeUploads) xhr.abort(); 
  activeUploads.clear();
  // empties the file metadata
  // dynamoDB is the source of the truth but the broswer still keeps a local copy
  // because the UI needs something to display immediately
  filesById.clear();
  // remove file and user html
  // ? means if result exists then do it if not dont crash just return undefined
  $("file-list")?.replaceChildren();
  $("user-email")?.replaceChildren();
  closeResultsModal();
} 
// displays the login interface
function showAuthScreen() {
  setVisible($("auth-screen"), true);
  setVisible($("app-screen"), false);
}
// after user signs in Cognito redirects back to app with auth code but its just needed once 
// dont want sitting in URL theres no reason to keep it visible bc app exhanged it for tokens
// get URL but loop thru unwanted fields 
function cleanCallbackUrl() {
  const url = new URL(window.location.href);

  for (const key of ["code", "state", "error", "error_description"]) {
    url.searchParams.delete(key);
  }
  // changes whats shown in the address bar
  // it doesnt reload the page
  history.replaceState({}, document.title, url.pathname + url.search + url.hash);
}

// defines the authentication check that runs when application starts
// runs when page starts loading so it runs on app open and when cognito redirects back to app
async function initAuth() {
    // parses URLs query parameters
  const params = new URLSearchParams(window.location.search);
    // check to see if cognito returned an OAuth error
  if (params.has("error")) {
    // gets error message then clears url then goes to login page and displays message
    const message = params.get("error_description") || params.get("error");
    // create a random secret then hash and broswer sends
    // then cognito returns the authorization code
    // broswer takes that authroization code and sends it with code verifier
    // cognito hashes the code verifier to see if matches then grants tokens
    // this protects against authorization code interception attacks
    sessionStorage.removeItem("sfi_code_verifier");

    // prevents cross state forgery attacks CSRF
    // it prevents unsolisated responses and makes sure callback belongs to login session that initiated it
    // app stores a state before redirecting to cognito to then compare when cognito sends back
    // broswer state abc to cognito then cognito state abc to broswer
    // broswer checks they match
    sessionStorage.removeItem("sfi_oauth_state");
    cleanCallbackUrl();
    showAuthScreen();
    showToast(message, "error");
    return;
  }
  // has cognito returned an auth code
  if (params.has("code")) {
    // read the auth code and state
    const code = params.get("code");
    const returnedState = params.get("state");
    const expectedState = sessionStorage.getItem("sfi_oauth_state");
    const verifier = sessionStorage.getItem("sfi_code_verifier");
    // deletes temp variables and clears url
    sessionStorage.removeItem("sfi_code_verifier");
    sessionStorage.removeItem("sfi_oauth_state");
    cleanCallbackUrl();

    try {
        // rejects if required values missing or returned state doesn't match
      if (!code || !verifier || !expectedState || returnedState !== expectedState) {
        throw new Error("Invalid sign-in response. Please sign in again.");
      }
        // send request to cognitos token endpoint
        // javascript waits for cognito to response
      const response = await fetch(`${COGNITO_URL}/oauth2/token`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: new URLSearchParams({
          grant_type: "authorization_code",  // tells cognito this request exchanges an authorization code
          client_id: CLIENT_ID,
          redirect_uri: REDIRECT_URI, // when you exchange auth code for tokens cognito expects same redirect URL
          code,  // auth code
          code_verifier: verifier  // verifier 
        })
      });

      // wait for JSON body to be converted into javascript object
      // if function returns a promise then its asynchronous 
      // common asynchronous are network requests, timer to expire and run callback, reading files, and websocket events
      const tokens = await response.json();
    // makes sure http response not missing anythign
      if (!response.ok || !tokens.access_token || !tokens.id_token) {
        throw new Error(tokens.error_description || tokens.error || "Sign-in failed.");
      }
      // stores tokens in memory
      accessToken = tokens.access_token;
      idToken = tokens.id_token;
      tokenExpiresAt = Date.now() + Number(tokens.expires_in || 3600) * 1000;

    // show authenticated application
      await showApp();
    } catch (error) {
      clearSession();
      showAuthScreen();
      showToast(error.message, "error");
    }

    return;
  }
  // not coming back from cognito so see if already token exits if not show login screen
  if (getAccessToken()) {
    await showApp();
  } else {
    showAuthScreen();
  }
}

async function signIn() {
  try {
    const verifier = randomString(); // generate the secret for PKCE 
    const state = randomString();  // genreate state value
    const digest = await crypto.subtle.digest( // compute hash of code verifier
      "SHA-256",
      new TextEncoder().encode(verifier)
    );
    // store values
    sessionStorage.setItem("sfi_code_verifier", verifier);
    sessionStorage.setItem("sfi_oauth_state", state);

    const url = new URL(`${COGNITO_URL}/oauth2/authorize`);
    // build its query parameters
    url.search = new URLSearchParams({
      response_type: "code", // request authorization code
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      scope: "openid email profile", // requests identity email and profile into
      state, // gives state value
      code_challenge: base64Url(new Uint8Array(digest)), // gives hashed verifier
      code_challenge_method: "S256"
    }).toString();

    // navigaets to cognito meaning http request is sent
    window.location.assign(url.href);
  } catch (error) {
    showToast(error.message || "Unable to start sign-in.", "error");
  }
}

function signOut() {
  clearSession();
  sessionStorage.removeItem("sfi_code_verifier");
  sessionStorage.removeItem("sfi_oauth_state");
    // creates cognitos logout url
    // must be done becaues cognito may store a login session cookie 
    // so say user logs out tokens deleted and user hits login again cognito could see cookie and log in no password required
  const url = new URL(`${COGNITO_URL}/logout`);
  url.search = new URLSearchParams({
    client_id: CLIENT_ID,
    logout_uri: LOGOUT_URI
  }).toString();

  window.location.assign(url.href);
}

// this is a general API helper
// inputs are http methods, API path, optional body, and optional concellatino signation
async function apiRequest(method, path, body = null, signal = undefined) {
  const token = getAccessToken();
  if (!token) throw new Error("Please sign in to continue.");

  // apends the path
  const response = await fetch(`${API_URL.replace(/\/$/, "")}${path}`, {
    method, // uses given method
    headers: { // remember access tokens are considered frontend visible
      Authorization: `Bearer ${token}`,  // send access token
      "Content-Type": "application/json"  // declare JSON content
    }, // ... is the spread operator it copies that property into the fetch options
    ...(body !== null ? { body: JSON.stringify(body) } : {}),
    ...(signal ? { signal } : {})
    // with a signal you create a controller that creates a signal
    // when you pass it to fetch now the request is listening to that signal
    // fetch creates a request object then starts http requests waits for response and resolves the promise
    // fetch holds reference to same object so it knows when signal aborted 
    // broswer can try to cancel the network operation but it way have already left so in that case fetch aborted and the response is discarded 
    // AbortController is just a javascript objet whose job is to manage cancellation
  });

  const text = await response.text();
  let data = null;

    // attempt to parse response as JSON if not store its text as a message
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text };
    }
  }
  // checks whether the http response is outside the successful 200-299 range
  if (!response.ok) {
    // 401 error means unauthorized so re login needed
    if (response.status === 401) {
      clearSession();
      showAuthScreen();
    }

    throw new Error(data?.message || `Request failed (${response.status}).`);
  }

  return data;
}

// accepts information needed to prepare an upload and returns API request
function getUploadUrl(fileName, contentType, fileSize) {
  return apiRequest("POST", "/files/upload", {
    fileName,
    contentType,
    fileSize
  });
}

// accepts an optional pagination cursor
function listFiles(lastKey = null) {
  const params = new URLSearchParams({ limit: "20" });
    // was cursor given
  if (lastKey !== null && lastKey !== undefined) {
    params.set( // if its already a string use it as is or convert to a string 
      "lastKey",
      typeof lastKey === "string" ? lastKey : JSON.stringify(lastKey)
    );
  }
  // make API request for file page
  // ? marks the start of the query string 
  return apiRequest("GET", `/files?${params}`);
}

// request files metadata and results from a fileID and optional signal
async function getFile(fileId, signal = undefined) {
  const result = await apiRequest("GET", `/files/${encodeURIComponent(fileId)}`, null, signal);
  return result; 
}

// ?? only uses next value if first is null or undefined
function fileIdOf(file) {
  return String(file.fileId ?? "");
}

// copies original properties then any properties that come after it overwrite existing ones wiht same name
// rest of code can safely do file.Id and file.processingStatus without worrying about variation
function normalizeFile(file) {
  return {
    ...file,
    fileId: fileIdOf(file),
    processingStatus: String(file.processingStatus || "PENDING").toUpperCase()
  };
}

// this function adds a file or updates an existing file
function upsertFile(file) {
  const fileId = fileIdOf(file);
  if (!fileId) return null;

  // overwrites new values with old values
  const normalized = normalizeFile({
    ...filesById.get(fileId),
    ...file,
    fileId
  });

    // updates or inserts the file
  filesById.set(fileId, normalized);
  // look for html element
  const container = $("file-list");
  // only update UI if that html element exists
  if (container) { // search all children by fileID
    const existing = Array.from(container.children).find(
      element => element.dataset.fileId === fileId
    ); // creates a new HTML for the file
    const card = renderFileCard(normalized);
    // if file already exists then update it if not add it
    if (existing) existing.replaceWith(card);
    else container.append(card);
  }
  // only show empty state if zero files
  setVisible($("empty-state"), filesById.size === 0);
  return normalized;
}
// this function loads and renders one file page
async function loadFiles(lastKey = null) {
  if (loadingFiles) return;  // prevents overlapping requests
    // active request
  loadingFiles = true;
  const version = sessionVersion;
  const button = $("load-more-btn");  
  // disables paginatino button during request
  if (button) button.disabled = true;

  try {
    // requests file page and discards outdated session response
    const response = await listFiles(lastKey);
    if (version !== sessionVersion) return;
    
    const files = Array.isArray(response)
      ? response
      : response?.items || [];
    // if this is a first page load then clear
    if (lastKey === null) {
      stopAllPolling();
      filesById.clear();
      $("file-list")?.replaceChildren();
    }
    // loop thru each returned file and render it
    for (const file of files) {
      const normalized = upsertFile(file);
        
      if (normalized && isProcessing(normalized.processingStatus)) {
        pollFileStatus(normalized.fileId);
      }
    }
    // stores cursor used to request the next page of files
    nextPageKey = response?.lastKey ?? null;

    // covert to null if empty
    if (
      nextPageKey === "" ||
      (typeof nextPageKey === "object" &&
        nextPageKey !== null &&
        Object.keys(nextPageKey).length === 0)
    ) {
      nextPageKey = null;
    }
    // shows or hides the load more button
    setVisible(button, nextPageKey !== null);
    // only shows empty state if no files cached
    setVisible($("empty-state"), filesById.size === 0);
  } catch (error) {
    if (version === sessionVersion) showToast(error.message, "error");
  } finally {
    loadingFiles = false;
    if (button) button.disabled = false;
  }
}

// send file bytes to s3
// presignedurl is the temporary s3 upload URL returned by backend 
// file is the broswers File object containing bytes to upload
function uploadFile(presignedUrl, file) {
     // creates and returns a Promise representing the upload
    // Promise constructor provides resolve and reject callbacks
return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(); // create http request object
    activeUploads.add(xhr); // adds request to set of active uploads
    // http uses PUT at the presigned URL
    xhr.open("PUT", presignedUrl);
    // sets uploads MIME type
    // MIME type is the files content type tells server what kind of file is being uploaded
    xhr.setRequestHeader(
      "Content-Type",
      file.type || "application/octet-stream"
    );

    // register a function that runs when teh broswer reports upload progress
    // this isnt related to the websocket its broswer telling your javascript how much of the file it has uploaded to the server
    // as bytes leave the broswer the broswer generates progress events
    // event => {  is same as function(event) { it means create a function that accepts one parameter named event
    xhr.upload.onprogress = event => {
        // exits if broswer cant determine total upload size
      if (!event.lengthComputable) return;
    // calculate uploaded percentage
    // finds html elements to display
      const percent = Math.round((event.loaded / event.total) * 100);
      const progress = $("upload-progress");
      const label = $("upload-progress-text");
        // only updates the progress element if it exists
      if (progress) {
        // make progress element visable
        setVisible(progress, true);
        // checks if element has value property and assings value to calculated percentage
        if ("value" in progress) {
          progress.max = 100;
          progress.value = percent;
        } else {
          progress.style.width = `${percent}%`;
          progress.setAttribute("role", "progressbar");
          progress.setAttribute("aria-valuenow", String(percent));
          progress.setAttribute("aria-valuemin", "0");
          progress.setAttribute("aria-valuemax", "100");
        }
      }
      // updates text label
      if (label) label.textContent = `${file.name}: ${percent}%`;
    };

    // registers handler for when servers http response arrives
    xhr.onload = () => {
        // remove request from active uplaod set bc finished
      activeUploads.delete(xhr);
        // status code 200 thru 299 are success and resolves promise
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed (${xhr.status}).`));
    };
    // registers handler for network level failures
    xhr.onerror = () => {
      activeUploads.delete(xhr);
      reject(new Error("Upload failed. Check your connection and S3 CORS settings."));
    };
    // registers handler for cancelled requests
    xhr.onabort = () => {
      activeUploads.delete(xhr);
      reject(new Error("Upload canceled."));
    };
    // registers handler for uplodds that take too long and timeout
    xhr.ontimeout = () => {
      activeUploads.delete(xhr);
      reject(new Error("Upload timed out."));
    };
    // set timeout to 15 minutes
    xhr.timeout = 15 * 60 * 1000;
    // fetch() you dont see the network details
    // but here im sending request manually
    // broswer takes actual file about and streams its raw bytes as request body
    // whereas in typical api call the request body contained json not the file itself
    xhr.send(file); 
  });
}

// this function checks a file before uploading
function validateFile(file) {
    // makes sure the argument is a broswer File and rejects a file containing zero bytes
  if (!(file instanceof File)) throw new Error("Choose a file to upload.");
  if (file.size === 0) throw new Error(`${file.name} is empty.`);

  // reads max size and blocks upload if file too large
  const input = $("file-input");
  const maxSize = Number(input?.dataset.maxSize);

  if (Number.isFinite(maxSize) && maxSize > 0 && file.size > maxSize) {
    throw new Error(`${file.name} exceeds the maximum upload size.`);
  }

  // takes file inputs accepted file types and turns them into a clean javascript array
  const accepted = (input?.accept || "")
    .split(",")
    .map(value => value.trim().toLowerCase())
    .filter(Boolean);

    // if no accepted types were configred then finish wihtout restricting file type
  if (!accepted.length) return;

  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();

  // checks wether at least one accept rule matches
  // .some() loops thru the array and stops as soon as one check returns true
  // looks at file name or type to see if an accepted type
  const allowed = accepted.some(value => {
    if (value.startsWith(".")) return name.endsWith(value);
    if (value.endsWith("/*")) return type.startsWith(value.slice(0, -1));
    return type === value;
  });

  if (!allowed) throw new Error(`${file.name} is not a supported file type.`);
}

// this defnies the entire full upload workflow
async function handleUpload(file) {
  const version = sessionVersion;

  try {
    validateFile(file);  // makes sure upload is of good type
    // gets MIME type and presigned url
    const contentType = file.type || "application/octet-stream";
    const response = await getUploadUrl(file.name, contentType, file.size);

    // make sure response contains valid and required fields
    if (version !== sessionVersion) return;
    if (!response?.uploadUrl || !response?.fileId) {
      throw new Error("The server did not return a valid upload URL.");
    }
    // upload the s3 bytes and wait for completion
    await uploadFile(response.uploadUrl, file);
    // check the session again
    if (version !== sessionVersion) return;
    // create local file card with pending status
    upsertFile({
      fileId: response.fileId,
      fileName: file.name,
      contentType,
      fileSize: file.size,
      uploadedAt: new Date().toISOString(),
      processingStatus: "PENDING"
    });
    // notifies the user and starts checking backend processing status
    showToast("Upload complete, processing...", "success");
    if (isWebSocketAvailable()) {
      // theres a single check done because processing could have been finished before files card was added 
      // so an earlier websocket message could be been ignored
      void refreshPendingFile(response.fileId);
    } else {
      pollFileStatus(response.fileId);
    }
  } catch (error) {
    if (version === sessionVersion) showToast(error.message, "error");
  }
}

// hanldes a collection of files uploaded
async function handleFiles(files) {
  // disable upload button
  const button = $("upload-btn");
  if (button) button.disabled = true;
  
  try { // converts file collection into array and loop thru each file
    for (const file of Array.from(files)) {
      // need access token
      if (!getAccessToken()) break;
      await handleUpload(file); // upload one file
    }
  } finally { // re enable upload button
    if (button) button.disabled = false;
    // clears file selction so you can upload same file
    const input = $("file-input");
    if (input) input.value = "";
    // hides the progress bar and clears its text now that uploading is done
    setVisible($("upload-progress"), false);
    const progressLabel = $("upload-progress-text");
    if (progressLabel) progressLabel.textContent = "";
  }
}

// converts status to uppercase text and returns true if PENDING OR PROCESSING
function isProcessing(processingStatus) {
  return ["PENDING", "PROCESSING"].includes(String(processingStatus).toUpperCase());
}

function pollFileStatus(fileId) {
  fileId = String(fileId);
  if (isWebSocketAvailable() || !getAccessToken()) return;
  if (!isProcessing(filesById.get(fileId)?.processingStatus)) return;
  if (pollingTimers.has(fileId)) return;

  const version = sessionVersion;
  const startedAt = Date.now();
  const controller = new AbortController();
  pollingControllers.set(fileId, controller);

  const isCurrent = () =>
    version === sessionVersion &&
    pollingControllers.get(fileId) === controller &&
    !controller.signal.aborted;

  const poll = async () => {
    if (!isCurrent()) return;

    if (isWebSocketAvailable() || !getAccessToken()) {
      stopPolling(fileId);
      return;
    }

    if (!isProcessing(filesById.get(fileId)?.processingStatus)) {
      stopPolling(fileId);
      return;
    }

    if (Date.now() - startedAt > 15 * 60 * 1000) {
      stopPolling(fileId);
      showToast("Processing is taking longer than expected. Refresh the file list later.");
      return;
    }

    try {
      const file = await getFile(fileId, controller.signal);
      if (!isCurrent() || isWebSocketAvailable()) return;

      const previousStatus = filesById.get(fileId)?.processingStatus;
      const updated = upsertFile({ ...file, fileId });

      if (updated && !isProcessing(updated.processingStatus)) {
        stopPolling(fileId);
        notifyStatus(updated, previousStatus);
        return;
      }
    } catch (error) {
      if (!isCurrent() || isWebSocketAvailable()) return;
    }

    if (isCurrent() && !isWebSocketAvailable()) {
      pollingTimers.set(fileId, setTimeout(poll, 3000));
    }
  };

  pollingTimers.set(fileId, setTimeout(poll, 3000));
}

// announces a changed file status
function notifyStatus(file, previousStatus) {
  // does nothing if no change
  if (file.processingStatus === previousStatus) return;
  // checks if processing succeeded or failed
  // shows a success or failure message
  if (file.processingStatus === "PROCESSED") {
    showToast(`${file.fileName || "File"} is ready.`, "success");
  } else if (file.processingStatus === "FAILED") {
    showToast(`${file.fileName || "File"} processing failed.`, "error");
  }
}

async function deleteFile(fileId) {
  const version = sessionVersion;
  // sends a httpe DELETE request for a file
  await apiRequest("DELETE", `/files/${encodeURIComponent(fileId)}`);
  if (version !== sessionVersion) return;

  fileId = String(fileId);
  // stop polling for deleted file
  // and remove it from local map
  stopPolling(fileId);
  filesById.delete(fileId);
  // selects cards whose id matches deleted file
  const container = $("file-list");
  const card = Array.from(container?.children || []).find(
    element => element.dataset.fileId === fileId
  );

  card?.remove();  // remove card
  setVisible($("empty-state"), filesById.size === 0);
  showToast("File deleted", "success");
}

// the websocket lets server push updates to the browser
function connectWebSocket(userId = getUserId()) {
  // need both a user ID and access token
  if (!userId || !getAccessToken()) return;
  // avoids creating another connectino if current socket is connecting or open
  if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
  // cancels any previously scheduled reconnect
  clearTimeout(reconnectTimer);
  const version = sessionVersion;

  // defines a helper for reconnecting later
  const scheduleReconnect = () => {
    if (version !== sessionVersion || !getAccessToken()) return;

    const delay = Math.min(3000 * 2 ** Math.min(reconnectAttempt++, 4), 30000);
    // dont schedule reconnect for outdate or unauthenticated session
    reconnectTimer = setTimeout(() => connectWebSocket(userId), delay);
  };

  try {
    const url = new URL(WS_URL);
    // adds or replaces userID query parameter for websocket URL
    url.searchParams.set("userId", userId);
    // creates a websocket and starts connected
    const connection = new WebSocket(url.href);
    // store it as the current socket
    socket = connection;
    // starts the fallback polling mechanism while live updates are unavaliable
    startFallbackPolling();

    // registers a function thatll run when connection opens
    connection.onopen = () => {
      // makes sure connection doesnt belong to old session
      if (version !== sessionVersion) {
        connection.close();
        return;
      }

      reconnectAttempt = 0;
      // stops polling now that live updates are available
      stopAllPolling();
      // loops thru all locally stored files
      for (const file of filesById.values()) {
        if (isProcessing(file.processingStatus)) {
          void refreshPendingFile(file.fileId, connection);
        }
      }
    };
    // registers a handler for incoming websocket messages 
    connection.onmessage = event => {
      if (version !== sessionVersion) return;

      try {
        // parse the websocket message
        const message = JSON.parse(event.data);
        const update = message;
        const fileId = String(update.fileId ?? "");
        // check for valid values
        if (!fileId || !update.processingStatus || !filesById.has(fileId)) return;
        // read files current status before changing it and store update
        const previousStatus = filesById.get(fileId).processingStatus;
        const file = upsertFile({ ...update, fileId });
        // stop polling if processing finished and announce a relevant status change
        if (!isProcessing(file.processingStatus)) stopPolling(fileId);
        notifyStatus(file, previousStatus);
      } catch {
        return;
      }
    };

    // close websocket connection if an error occurs
    connection.onerror = () => connection.close();
    // registers a handler for connection closure
    connection.onclose = () => {
      if (socket !== connection) return;
      socket = null;
      startFallbackPolling(); // starts backup polling and then schedules reconnect
      scheduleReconnect();
    };
  } catch {
    socket = null;
    startFallbackPolling();
    scheduleReconnect();
  }
}

// this function constructs and returns a files HTML card
// an HTML card is a design concept usually built from one or more HTML elments (usally a <div>)
// and styled with CSS to display related context
function renderFileCard(file) {
  // <div> is one of the most common HTML elements
  // its an empty box that holds other HTML elements
  // a class lets you group HTML elements together under a shared name
  // file-card is a class here
  const card = createElement("div", "file-card");
  // the attribute doesnt have to exist before hand the broswer creates the HTML attribute for you
  card.dataset.fileId = fileIdOf(file);
  // finds the files content type liek image/png
  const contentType = file.contentType || file.type || "";
  // creates a file icon
  const icon = createElement(
    "span", // type of html element
    "file-icon", // html class
    contentType.startsWith("image/") ? "🖼️" : "📄"
  );
  // put this asccessibility attribute true so on the icon screen readers ignore the decorative emoji
  icon.setAttribute("aria-hidden", "true");
  // create a heading showing the file name
  const title = createElement("h3", "file-name", file.fileName || "Untitled");
  // parses for upload data and creates data label
  const date = new Date(file.uploadedAt || "");
  const dateLabel = createElement(
    "p",
    "file-date",
    Number.isNaN(date.getTime()) ? "" : date.toLocaleString()
  );
  // normalizes status to uppercase and defaults to pending
  const processingStatus = String(file.processingStatus || "PENDING").toUpperCase();
  // creates the status badge
  const badge = createElement(
    "span",
    `status-badge status-${processingStatus.toLowerCase().replace(/[^a-z0-9_-]/g, "")}`,
    processingStatus
  );
  // creates a container for action buttons
  const actions = createElement("div", "file-actions");

  // only creates a results button for successfully processed files
  if (processingStatus === "PROCESSED") {
    // button for reviewing the results
    const viewButton = createElement("button", "view-results-btn", "View Results");
    viewButton.type = "button";  // this button is just for running javascript dont submit a form
    // when someone clicks this button run this funciton
    viewButton.addEventListener("click", event => {
      event.stopPropagation(); // dont let click event go to parent elements
      showResults(file);
    });  // add button to the actions div container
    actions.append(viewButton);
  }

  // delete button 
  const deleteButton = createElement("button", "delete-btn", "Delete");
  deleteButton.type = "button";
  deleteButton.addEventListener("click", async event => {
    event.stopPropagation();

      // display a confirmation dialog
    if (!window.confirm(`Delete "${file.fileName || "this file"}"?`)) return;
    // prevents repeated licks
    deleteButton.disabled = true;
    // get hte file id and delete
    try {
      await deleteFile(fileIdOf(file));
    } catch (error) {
      showToast(error.message, "error");
      deleteButton.disabled = false;
    }
  });
  // add delete button to dev container
  actions.append(deleteButton);
  // adds the cards elements in that order
  card.append(icon, title, dateLabel, badge, actions);

  card.addEventListener("click", event => {
    // ignores clicks insdie a button
    if (event.target.closest("button")) return; 
    // opens results when the card represents a processed file
    if (processingStatus === "PROCESSED") showResults(file);
  });

  return card;
}

// returns the results popup container
function getResultsModal() {
  let modal = $("results-modal");
  // looks ofr an existing modal and creates one if missing
  // a modal is a pop up widnows that appears on top of the current page and demands users attention
  // css looks at model label attached and makes it behave that way
  if (!modal) {
    modal = createElement("div", "modal");
    modal.id = "results-modal";
    modal.hidden = true; // hides it at first
    document.body.append(modal); // put the modal inside the body as a child element
  }
  return modal;
}

// this function fills and displays the results popup
function renderResultsModal(file) {
  const modal = getResultsModal(); // gets or creates its outer container
  let content = modal.querySelector(".modal-content");  // looks inside for element with class modal content
  // creates inner container if needed
  if (!content) {
    content = createElement("div", "modal-content");
    modal.append(content);
  }

  const results = file.results || file.result || {};
  // creates the close button
  const closeButton = createElement("button", "modal-close", "Close");
  closeButton.type = "button";
  closeButton.addEventListener("click", closeResultsModal);
  // creates a heading using the filename
  const title = createElement("h2", "", file.fileName || "File Results");
  title.id = "results-modal-title"; // id is needed when something else needs to refer to that specific element later
  // creates a description list for label and value information 
  const metadata = createElement("dl", "file-metadata");
  const date = new Date(file.uploadedAt || "");
  // starts an array of metadata pairs
  const entries = [
    ["Type", file.contentType || file.type || "Unknown"],
    ["Size", Number.isFinite(Number(file.fileSize)) ? `${Number(file.fileSize).toLocaleString()} bytes` : "Unknown"],
    ["Status", file.processingStatus || "Unknown"],
    ["Uploaded", Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString()]
  ];
  // loops thru the pairs 
  for (const [label, value] of entries) {
    metadata.append(createElement("dt", "", label), createElement("dd", "", value));
  } // adds a description term for label and description for its value
  // creates the summary heading
  const summaryTitle = createElement("h3", "", "Summary");
  const summary = createElement( // creates summary paragraph
    "p",
    "results-summary",
    results.summary ?? file.summary ?? "No summary available."
  );
  // creates an expandable details section 
  const details = createElement("details", "extracted-text");
  details.append( // two elements inside details
    createElement("summary", "", "Extracted Text"),   // clickable heading for expanding and collapsing the section
    createElement( // preserve spaces tbales and line breaks
      "pre", // its hidden until not collasped
      "",
      results.extractedText ?? results.text ?? file.extractedText ?? "No extracted text available."
    ) // summary is the clickable label and pre is the shown content when expanded
  );

  const labelsTitle = createElement("h3", "", "Entities and Labels");
  const labelsList = createElement("ul", "results-labels"); // ul is unordered
  const labels = [
    results.entities ?? file.entities ?? [],
    results.labels ?? file.labels ?? []
  ].flatMap(value => Array.isArray(value) ? value : [value]);

  for (const label of labels) {
    const text = typeof label === "string"
      ? label
      : label?.text || label?.Text || label?.name || label?.Name || JSON.stringify(label);

    if (text) labelsList.append(createElement("li", "", text));
  }

  if (!labelsList.children.length) {
    labelsList.append(createElement("li", "", "No entities or labels available."));
  }

  const downloadButton = createElement("button", "download-original-btn", "Download Original");
  downloadButton.type = "button";

  downloadButton.addEventListener("click", async () => {
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    downloadButton.disabled = true;

    try {
      const latest = await getFile(fileIdOf(file));
      if (!latest.downloadUrl) throw new Error("Download URL is unavailable.");

      const url = new URL(latest.downloadUrl);
      if (url.protocol !== "https:") throw new Error("Invalid download URL.");

      if (tab) tab.location.replace(url.href);
      else throw new Error("Allow pop-ups to download the original file.");
    } catch (error) {
      tab?.close();
      showToast(error.message, "error");
    } finally {
      downloadButton.disabled = false;
    }
  });

  content.replaceChildren(
    closeButton,
    title,
    metadata,
    summaryTitle,
    summary,
    details,
    labelsTitle,
    labelsList,
    downloadButton
  );

  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", title.id);

  if (typeof modal.showModal === "function") {
    modal.hidden = false;
    modal.style.display = "";
    if (!modal.open) modal.showModal();
  } else {
    setVisible(modal, true);
  }

  closeButton.focus();
}

async function showResults(file) {
  const version = sessionVersion;

  try {
    // get latest file data from server
    const latest = await getFile(fileIdOf(file));
    if (version !== sessionVersion) return;
    // display file if updated
    const updated = upsertFile(latest);
    if (updated) renderResultsModal(updated);
  } catch (error) {
    if (version === sessionVersion) showToast(error.message, "error");
  }
}

function closeResultsModal() {
  const modal = $("results-modal");
  if (!modal) return;
  // calls modal close if supported and open
  if (typeof modal.close === "function" && modal.open) modal.close();
  setVisible(modal, false);
}

// display a temporary notification 
// defaults to an informal message
function showToast(message, type = "info") {
  let container = $("toast-container");

  if (!container) {
    container = createElement("div", "toast-container");
    container.id = "toast-container";
    container.setAttribute("aria-live", "polite");
    // browswer auto creats an object called document that represents entire page
    document.body.append(container);
    // everything the user sees is usually inside the body
  }
  // only allows some notification types
  const safeType = ["info", "success", "error", "warning"].includes(type) ? type : "info";
  const toast = createElement("div", `toast toast-${safeType}`, message);
  toast.setAttribute("role", safeType === "error" ? "alert" : "status");
  container.append(toast);
  setTimeout(() => toast.remove(), 4000);
}

async function showApp() {
  // sees if auth is missing
  if (!getAccessToken()) {
    showAuthScreen();
    return;
  }
  // change screen
  setVisible($("auth-screen"), false);
  setVisible($("app-screen"), true);
  // displays users email
  const email = $("user-email");
  if (email) email.textContent = decodeToken(idToken).email || "";
  // prevents duplicate websocket connections
  if (appStarted) return;
  appStarted = true;

  connectWebSocket();
  await loadFiles();
}

function initialize() {
  // attaches click handlers
  $("sign-in-btn")?.addEventListener("click", signIn);
  $("sign-out-btn")?.addEventListener("click", signOut);

  const input = $("file-input");
  const dropZone = $("drop-zone");
  const uploadButton = $("upload-btn");

  // when users selects files pass the selection to handleFiles
  input?.addEventListener("change", () => handleFiles(input.files));

  // opens for user
  uploadButton?.addEventListener("click", event => {
    event.preventDefault();
    input?.click();
  });

  let dragDepth = 0;

  dropZone?.addEventListener("dragenter", event => {
    event.preventDefault();
    dragDepth += 1;
    dropZone.classList.add("drag-over");
  });

  dropZone?.addEventListener("dragover", event => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });

  dropZone?.addEventListener("dragleave", event => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) dropZone.classList.remove("drag-over");
  });

  dropZone?.addEventListener("drop", event => {
    event.preventDefault();
    dragDepth = 0;
    dropZone.classList.remove("drag-over");
    if (event.dataTransfer?.files.length) handleFiles(event.dataTransfer.files);
  });

    // registers handler for load more button
  $("load-more-btn")?.addEventListener("click", () => {
    if (nextPageKey !== null) loadFiles(nextPageKey);
  });

  document.addEventListener("click", event => {
    if (event.target === $("results-modal")) closeResultsModal();
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeResultsModal();
  });

    // starts authenticatino initialization and attaches error handler
  initAuth().catch(error => {
    showAuthScreen();
    showToast(error.message || "Unable to initialize the application.", "error");
  });
}

// runs intialize() once broswer is done parsing the HTML document
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize, { once: true });
} else {
  initialize();
}