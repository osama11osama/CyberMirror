# External Tools — Reference Only

The folders in `../OSINT_tools/` (Maigret, Sherlock, Holehe, etc.) are kept for **learning and research**.

**CyberMirror does NOT use them at runtime.**

## What We Learned From Each

| Tool | Concept Adopted in CyberMirror |
|------|-------------------------------|
| Maigret / Sherlock | Username platform scanning → `modules/username/scanner.py` + `sites.json` |
| Holehe | Email exposure detection → `modules/email/scanner.py` |
| WhatsMyName | Site detection patterns → our own `sites.json` schema |
| SpiderFoot | Unified dashboard + correlation → Dashboard + Graph |
| personal-osint-audit | Query builder + risk engine → `modules/identity/queries.py` |

## Your Code vs Their Code

Everything in `backend/app/modules/` is **original CyberMirror code**.  
You own it. You can extend it. You can sell it (with proper legal review).

Do not copy GPL/AGPL source code from external tools into CyberMirror modules.
