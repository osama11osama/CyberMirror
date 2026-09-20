# Username Catalog Attribution

CyberMirror's username scanner uses two data sources:

- `sites.json` — a small fallback catalog committed with the project;
- an optional external WhatsMyName `wmn-data.json` file supplied at runtime.

## WhatsMyName attribution

WhatsMyName is maintained at:

https://github.com/WebBreacher/WhatsMyName

The upstream project states that its dataset is licensed under **CC BY-SA 4.0** and attributes the work to **Micah Hoffman and contributors**.

Some fallback definitions in `sites.json` are adapted from or cross-checked against WhatsMyName site-detection information. To keep the provenance unambiguous, the complete `sites.json` fallback data file is made available under the same **CC BY-SA 4.0** terms.

License:

https://creativecommons.org/licenses/by-sa/4.0/

This notice applies to the fallback **data file**, not to the CyberMirror Python source code that loads or evaluates the data.

## Contributions

When adding a new fallback entry:

1. prefer independently verified public profile URLs and detection behavior;
2. record third-party provenance when a definition is adapted from another dataset;
3. preserve any license/attribution requirements;
4. do not copy third-party program source code into the scanner.
