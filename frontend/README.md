# Chekiz frontend

The frontend is plain HTML, CSS, and JavaScript. It has no build step or package dependencies.

## Run it locally

From the repository root, start the backend:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend also needs Tesseract OCR installed and available on `PATH`; see the repository README for platform-specific setup.

Open <http://localhost:8000>. FastAPI serves the frontend and API together; no second server is needed. The Docker image includes both. The frontend uses its own origin for API requests, including when running on another port or an HTTPS host. Camera access works on `localhost` or an HTTPS site. For separate static hosting, set the backend address in [`config.js`](./config.js).

The browser sends `X-API-Key` when a key is saved in **Payment desk → Connection settings**. The value is kept in that browser’s local storage. If the backend has no `CHECKIZ_API_KEY`, leave the field empty. A wrong key is reported in the page and the affected sections can be retried.

The dashboard polls `/orders`, `/history`, `/pending`, and `/stats`. Receipt verification posts the selected image and order ID to `/verify`; the file is not previewed or saved by the frontend. Pasted wallet alerts use `/ledger/sms`. QR Ph registration and one-order QR generation use the backend’s `/qr/*` routes.

## Use the overlay in OBS

1. In OBS, add a **Browser Source** and set its URL to `http://localhost:3000/overlay.html`.
2. Set a canvas size around **760 × 190 px**. Leave the background transparent.
3. If needed, supply a backend URL and API key as query parameters:

   ```text
   http://localhost:3000/overlay.html?api=http%3A%2F%2Flocalhost%3A8000&key=YOUR_API_KEY
   ```

   `api` and `key` are optional; the defaults are the configured API URL and the key saved by the payment desk. The overlay checks `/history?limit=1` every 2.5 seconds.

The overlay URL’s `key` query parameter is visible in OBS source settings and browser history. Do not put a production key in a public URL or share the source settings; use a trusted backend and protect access to the OBS machine.

## Deploy as static files

Upload the contents of this folder (`index.html`, `qr.html`, `overlay.html`, `styles.css`, `config.js`, `shared.js`, `dashboard.js`, `qr.js`, and `camera.js`) to any static host. Before publishing, set `apiBaseUrl` in `config.js` to the HTTPS URL of the backend. The backend must allow the deployed site’s origin through CORS; restrict CORS to your own domain for production.

Static hosting does not make the backend private. Do not place secrets in `config.js`; browser requests and the OBS query string are visible to the person using them. Use HTTPS for both the static site and the API, protect the API with `CHECKIZ_API_KEY`, and follow the backend’s production security guidance before handling real payments.
