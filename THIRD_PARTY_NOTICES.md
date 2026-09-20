# Third-Party Notices

CyberMirror is maintained as a separate application. Third-party software, data, APIs, websites, and trademarks remain the property of their respective owners.

This file documents integrations that are relevant to the current repository. Historical experiments with unrelated OSINT tools are not dependencies of the current codebase.

## WhatsMyName

Project: https://github.com/WebBreacher/WhatsMyName

CyberMirror can optionally load the WhatsMyName `wmn-data.json` dataset at runtime to extend username-site coverage.

WhatsMyName states that its dataset is licensed under the **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)** license and attributes the work to Micah Hoffman and contributors.

CyberMirror does not vendor the upstream `wmn-data.json` file. Users obtain it separately.

Some definitions in CyberMirror's small fallback catalog (`backend/app/modules/username/sites.json`) are adapted from or cross-checked against WhatsMyName detection data. To avoid ambiguity, that fallback data file is treated as CC BY-SA 4.0 material. See `backend/app/modules/username/ATTRIBUTION.md`.

## Have I Been Pwned

Service: https://haveibeenpwned.com/

CyberMirror can query the HIBP API when a user provides an API key. HIBP is an external service; its API terms, rate limits, and usage requirements apply independently of CyberMirror.

No HIBP source code or breach database is distributed in this repository.

## Python dependencies

Backend dependencies are declared in `backend/requirements.txt`, including FastAPI, Pydantic, HTTPX, DDGS, python-whois, Playwright, cryptography, and xhtml2pdf.

These packages are installed from their normal distribution channels and remain under their upstream licenses. CyberMirror does not relicense them.

## JavaScript dependencies

Frontend dependencies are declared in `frontend/package.json` and locked in `frontend/package-lock.json`. They include Angular, Angular Material, Cytoscape.js, ECharts, PrimeNG, RxJS, and related packages.

The optional desktop wrapper uses Electron and electron-builder as declared in `desktop/package.json`.

These dependencies remain under their upstream licenses.

## External websites and APIs

CyberMirror performs normal HTTP/browser requests to public websites and selected external endpoints as part of self-audit scans. Platform names and trademarks are used only to identify the service being checked and remain the property of their respective owners.

External endpoints can change or restrict automated access. Users are responsible for complying with applicable service terms and law.

## Distribution note

If CyberMirror is packaged into a redistributable binary or commercial product, dependency licenses and required notices should be reviewed again for the exact versions being distributed.
