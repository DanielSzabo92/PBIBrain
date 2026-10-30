# How does the app read and write cloud models through XMLA?

Type: research
Status: resolved
Blocked by: 

## Question

Which client library fits the existing .NET bridge? How does interactive Microsoft account sign-in work from a desktop app? How does the app read the full metadata, export it as TMDL, and deploy only the changes? Which conditions must the app test before a write (capacity setting, enhanced metadata, permissions, Desktop-authored model)? What are the known limits and failure modes?

## Answer

Findings: branch `research/xmla-access`, file `.scratch/dev-center/research/02-xmla-access.md` (not merged, not pushed). Some source URLs in that file need a check.

- Library: Microsoft.AnalysisServices (TOM) in the existing .NET bridge. Add a separate cloud command. Keep the offline mode unchanged. Consider an update from 19.114.12 to the current version.
- Sign-in: MSAL.NET public client with a dedicated Entra app registration. Silent token first, then interactive. Prefer the Windows broker (WAM). Use a persistent MSAL token cache (Windows-protected), not session files.
- The bridge receives the token through `Server.AccessToken` (or the connection string) and handles token expiry.
- Read and pull: TOM reads the full model, and TmdlSerializer exports it as TMDL.
- Write: `Model.SaveChanges()` sends only the changed objects. There is no documented "diff a TMDL folder against a live model" call. The app must apply the Change Plan to the TOM objects itself.
- Test before a write: the workspace is on Premium, PPU, Fabric, or Embedded capacity; the user has the Contributor role or higher. There is no documented client call for the capacity XMLA setting, enhanced metadata, or "authored in Desktop". The app must treat the write error as the signal, and explain it in plain words.
- Risks: an XMLA write blocks the PBIX download. A later PBIX republish overwrites the incremental refresh policy. A metadata-only deploy keeps the partitions. XMLA cannot set data source credentials. Live-connected, push, and Excel models do not support it.
- Open: Entra app registration and consent, token hand-off from Python to the bridge, personal accounts, and tests with a real workspace (none done).
