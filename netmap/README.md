# netmap — live network map (SUNSU / 21 Sunpassion)

Interactive, auto-refreshing topology of the whole fleet: WAN → FortiGate → VLANs,
Wi-Fi, site-to-site tunnels, and Azure hub-spoke. Drawn once from a fixed map and
overlaid with **live status** (up / warn / down) on every poll — the way an NMS
map works.

Stack: FastAPI + vanilla JS (Cytoscape.js) + Docker. Read-only; never writes to
any device.

## Run it

```bash
docker compose up -d --build
# open http://<nas>:8700
```

It starts in **mock** mode (the 2026-11-05 snapshot) so it looks right with zero
credentials. Everything is interactive: drag nodes (layout is saved per browser),
zoom/pan, tap a node for details, Fit / Reset buttons, light/dark toggle.

## Go live (real-time)

Point it at your IT Infra MCP and flip the collector:

```yaml
environment:
  COLLECTOR: "mcp"
  MCP_URL:   "https://mcp.21sunpassion.com/mcp"
  MCP_TOKEN: "<bearer token for the MCP>"
  POLL_SECONDS: "30"
```

The live collector overlays status from the same read tools the map was built from:

| Map node(s)                     | MCP tool                     |
|---------------------------------|------------------------------|
| WAN1/2/3                        | `fortigate_interfaces`       |
| FortiGate, VLANs                | `fortigate_status`           |
| Azure/Kitchen/iNET/Home tunnels | `fortigate_ipsec_tunnels`    |
| AP-01…06                        | `meraki_device_statuses`     |
| Cisco SW-01                     | `cisco_status`               |
| vm-sunsu-bi / sap-b1-app / -db  | `azure_vms`                  |
| dwhbi SQL MI                    | `azure_sql`                  |
| Proxmox pve01 (host)            | `proxmox_nodes`              |
| pve01 guests (AD01/NAS/VM107)   | `proxmox_vms`                |

> **Proxmox note:** `proxmox_nodes` reports the host up/down with any token, but
> listing guests (`proxmox_vms`) needs the API token to have **PVEAuditor on `/`**
> (Datacenter → Permissions → API Token Permission). Until that is granted, the
> pve01 host shows live online/offline and its guest VMs stay `unknown` (grey).
> Guest name matching lives in `collect_mcp` → `guest_names`; adjust it to your
> actual VM names / VMIDs on pve01.

`collector.py` is the only file to touch:
- **Transport/auth** differs on your MCP? Adjust `MCP._post` / `_headers`
  (it speaks standard MCP streamable-HTTP JSON-RPC with a bearer token today).
- Bare tool names rejected? set `MCP_TOOL_PREFIX="IT_Infra."`.
- Any single tool failing just leaves those nodes `unknown`; the map still draws.

If `COLLECTOR=mcp` can't reach the MCP at all, the app falls back to the snapshot
and says so in the footer, so the page is never blank.

## Editing the map

Topology (nodes, edges, coordinates, zones) lives at the top of `collector.py` in
`NODES` / `EDGES`. It changes rarely; the live layer only overlays status, so a new
switch or VLAN is a one-line edit there.

## Deploy (Portainer Git stack)

Push to a repo under `nont-naraphat`, add a Portainer **Git stack** pointing at it,
or `docker compose up -d --build` over SSH if the Git stack is stale.

## Notes

- `POLL_SECONDS` = backend refresh cadence; the browser re-polls every 20s and
  pulses any node whose status changed.
- The front-end loads Cytoscape from cdnjs. To run fully offline, vendor
  `cytoscape.min.js` into `static/` and change the `<script src>` in `index.html`.
