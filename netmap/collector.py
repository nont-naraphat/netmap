"""
netmap collector: builds the live network topology for the web map.

Design (NMS pattern): the MAP is drawn once from a fixed topology skeleton
(nodes + edges, with layout coordinates). The LIVE layer only overlays STATUS
on each node every poll -- exactly how a real network map works.

Two collectors, chosen by env COLLECTOR:
  - "mock"  (default): overlays the real snapshot captured 2026-11-05 so the
             app runs and looks right immediately, no credentials needed.
  - "mcp":   overlays live status pulled from the IT Infra MCP server
             (mcp.21sunpassion.com) using the same read tools the map was
             built from. Set COLLECTOR=mcp + MCP_URL + MCP_TOKEN to enable.

Topology (ids/edges) rarely changes; when it does, edit the skeleton below.
ASCII-only comments (SunPassion convention).

STATUS values: up | warn | down | unknown
"""

import os
import json
import uuid
from datetime import datetime, timezone, timedelta

import requests

BKK = timezone(timedelta(hours=7))

# --------------------------------------------------------------- skeleton

# x,y are model coordinates for the preset layout (the "map").
# zone draws the group box; type drives the icon + color.
# NODES: id, label, sub, type, zone, x, y
NODES = [
    # internet / wan (top spine)
    ("INTERNET", "Internet", "3 ISP uplinks", "internet", "internet", 850, 60),
    ("WAN1", "WAN1 Symphony", "83.118.10.145/31", "wan", "wan", 600, 185),
    ("WAN2", "WAN2 AIS", "192.168.11.37", "wan", "wan", 850, 185),
    ("WAN3", "WAN3 AIS", "192.168.10.38", "wan", "wan", 1100, 185),
    # core
    ("FGT", "FortiGate 120G", "FortiOS 7.4.11", "fw", "core", 850, 320),
    # LEFT column -- campus LAN + wifi
    ("SW01", "Cisco C1300 SW-01", "48-port PoE", "switch", "campus", 300, 460),
    ("BRIDGE2", "Server LAN", "192.168.0.0/24", "lan", "campus", 560, 460),
    ("AP01", "AP-01", "MR36", "ap", "campus", 90, 575),
    ("AP02", "AP-02", "MR36", "ap", "campus", 200, 575),
    ("AP03", "AP-03", "MR36", "ap", "campus", 310, 575),
    ("AP04", "AP-04", "gi3", "ap", "campus", 420, 575),
    ("AP05", "AP-05", "MR36", "ap", "campus", 530, 575),
    ("AP06", "AP-06 temp", "MR36", "ap", "campus", 640, 575),
    # LEFT column -- virtualization (Proxmox pve01 + guests)
    ("PVE", "Proxmox pve01", "192.168.0.10", "host", "virt", 370, 760),
    ("ADSRV", "AD01 (DC/DNS)", "192.168.0.4", "server", "virt", 230, 880),
    ("NASVM", "XPEnology NAS VMs", "ArcLoader", "server", "virt", 390, 880),
    ("FMG", "FortiManager VM107", "fmg mgmt", "server", "virt", 550, 880),
    # LEFT column -- vlans
    ("V2", "VLAN2 Staff", "192.168.110.1/23", "vlan", "vlans", 130, 1065),
    ("V3", "VLAN3 Guest", "192.168.120.1/24", "vlan", "vlans", 300, 1065),
    ("V4", "VLAN4 Printer", "192.168.150.1/24", "vlan", "vlans", 470, 1065),
    ("V5", "VLAN5 SAP", "192.168.160.1/24", "vlan", "vlans", 640, 1065),
    ("V9", "VLAN9 CCTV", "192.168.130.1/24", "vlan", "vlans", 130, 1175),
    ("V10", "VLAN10 IT.Admin", "192.168.140.1/24", "vlan", "vlans", 300, 1175),
    ("V90", "VLAN90 Bypass", "192.168.90.1/24", "vlan", "vlans", 470, 1175),
    ("V99", "VLAN99 MGNT", "192.168.99.1/24", "vlan", "vlans", 640, 1175),
    # RIGHT column -- azure cloud
    ("AZVPN", "S2S IPsec Gateway", "85.211.229.245", "vpn", "cloud", 1070, 460),
    ("HUB", "Hub VNet", "10.100.0.0/16", "vnet", "cloud", 1330, 460),
    ("BI", "Spoke BI", "10.101.0.0/23", "vnet", "cloud", 1150, 605),
    ("SAP", "Spoke SAP B1", "10.102.0.0/24", "vnet", "cloud", 1430, 605),
    ("DWHBI", "dwhbi SQL MI", "4 vCore", "db", "cloud", 1060, 745),
    ("VMBI", "vm-sunsu-bi", "Windows", "server", "cloud", 1210, 745),
    ("SAPAPP", "sap-b1-app", "10.102.0.4", "server", "cloud", 1370, 745),
    ("SAPDB", "sap-b1-db", "10.102.0.5", "db", "cloud", 1530, 745),
    # RIGHT column -- remote sites (site-to-site)
    ("KITCHEN", "FG-to-Kitchen C", "192.168.1.0/24", "tunnel", "sites", 1090, 930),
    ("INET", "to-iNET", "192.168.2.0/24", "tunnel", "sites", 1270, 930),
    ("HOME", "Home (MikroTik)", "172.27.53.0/24", "tunnel", "sites", 1450, 930),
    ("BS", "IPsec to BS", "standby", "tunnel", "sites", 1180, 1040),
    ("VMSUP", "VMSupport", "standby", "tunnel", "sites", 1360, 1040),
    # RIGHT column -- remote access
    ("SSLVPN", "SSL-VPN", "ssl.root", "remote", "remote", 1180, 1200),
    ("L2TP", "L2TP", "10.10.0.0/16", "remote", "remote", 1360, 1200),
]

# EDGES: id, source, target, type, label
EDGES = [
    ("e1", "INTERNET", "WAN1", "wan", ""),
    ("e2", "INTERNET", "WAN2", "wan", ""),
    ("e3", "INTERNET", "WAN3", "wan", ""),
    ("e4", "WAN1", "FGT", "wan", "primary"),
    ("e5", "WAN2", "FGT", "wan", ""),
    ("e6", "WAN3", "FGT", "wan", ""),
    ("e7", "FGT", "SW01", "trunk", "VLAN trunk"),
    ("e8", "FGT", "BRIDGE2", "lan", ""),
    ("e8b", "BRIDGE2", "PVE", "lan", ""),
    ("e9", "PVE", "ADSRV", "host", "hosts"),
    ("e10", "PVE", "NASVM", "host", "hosts"),
    ("e11", "PVE", "FMG", "host", "hosts"),
    ("ea1", "SW01", "AP01", "wifi", ""),
    ("ea2", "SW01", "AP02", "wifi", ""),
    ("ea3", "SW01", "AP03", "wifi", ""),
    ("ea4", "SW01", "AP04", "wifi", ""),
    ("ea5", "SW01", "AP05", "wifi", ""),
    ("ea6", "SW01", "AP06", "wifi", ""),
    ("ev2", "SW01", "V2", "vlan", ""),
    ("ev3", "SW01", "V3", "vlan", ""),
    ("ev4", "SW01", "V4", "vlan", ""),
    ("ev5", "SW01", "V5", "vlan", ""),
    ("ev9", "SW01", "V9", "vlan", ""),
    ("ev10", "SW01", "V10", "vlan", ""),
    ("ev90", "SW01", "V90", "vlan", ""),
    ("ev99", "SW01", "V99", "vlan", ""),
    ("ez1", "FGT", "AZVPN", "vpn", "S2S IPsec"),
    ("ez2", "AZVPN", "HUB", "vnet", ""),
    ("ez3", "HUB", "BI", "peer", "peering"),
    ("ez4", "HUB", "SAP", "peer", "peering"),
    ("ez5", "BI", "DWHBI", "data", ""),
    ("ez6", "BI", "VMBI", "data", ""),
    ("ez7", "SAP", "SAPAPP", "data", ""),
    ("ez8", "SAP", "SAPDB", "data", ""),
    ("es1", "FGT", "KITCHEN", "vpn", ""),
    ("es2", "FGT", "INET", "vpn", ""),
    ("es3", "FGT", "HOME", "vpn", ""),
    ("es4", "FGT", "BS", "vpn", ""),
    ("es5", "FGT", "VMSUP", "vpn", ""),
    ("er1", "FGT", "SSLVPN", "remote", ""),
    ("er2", "FGT", "L2TP", "remote", ""),
]

ZONE_LABELS = {
    "internet": "Internet",
    "wan": "WAN uplinks (SD-WAN)",
    "core": "Core firewall",
    "campus": "HQ LAN & Wi-Fi",
    "virt": "Virtualization \u00b7 pve01",
    "vlans": "Internal VLANs",
    "cloud": "Microsoft Azure (malaysiawest)",
    "sites": "Remote sites (IPsec)",
    "remote": "Remote access",
}

# snapshot captured 2026-11-05 (used by the mock collector)
MOCK_STATUS = {
    "INTERNET": "up", "WAN1": "up", "WAN2": "up", "WAN3": "up", "FGT": "up",
    "SW01": "up", "BRIDGE2": "up", "ADSRV": "up", "PVE": "up",
    "NASVM": "up", "FMG": "up",
    "AP01": "up", "AP02": "up", "AP03": "up", "AP04": "warn", "AP05": "up", "AP06": "up",
    "V2": "up", "V3": "up", "V4": "up", "V5": "up", "V9": "up", "V10": "up", "V90": "up", "V99": "up",
    "AZVPN": "up", "HUB": "up", "BI": "up", "SAP": "up",
    "DWHBI": "up", "VMBI": "up", "SAPAPP": "warn", "SAPDB": "warn",
    "KITCHEN": "up", "INET": "up", "HOME": "up", "BS": "down", "VMSUP": "down",
    "SSLVPN": "up", "L2TP": "up",
}


def _skeleton():
    nodes = []
    for nid, label, sub, typ, zone, x, y in NODES:
        nodes.append({"id": nid, "label": label, "sub": sub, "type": typ,
                      "zone": zone, "x": x, "y": y, "status": "unknown"})
    edges = []
    for eid, s, t, typ, label in EDGES:
        edges.append({"id": eid, "source": s, "target": t, "type": typ,
                      "label": label, "status": "unknown"})
    return nodes, edges


def _finalize(nodes, edges, source):
    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        tgt = by_id.get(e["target"], {})
        if e["type"] in ("vpn", "peer") and tgt.get("status") in ("down", "warn", "up"):
            e["status"] = tgt["status"]
        else:
            s = by_id.get(e["source"], {}).get("status", "unknown")
            t = tgt.get("status", "unknown")
            e["status"] = "down" if "down" in (s, t) else (
                "up" if "up" in (s, t) else "unknown")
    counts = {"up": 0, "warn": 0, "down": 0, "unknown": 0}
    for n in nodes:
        counts[n.get("status", "unknown")] = counts.get(n.get("status", "unknown"), 0) + 1
    return {
        "nodes": nodes, "edges": edges,
        "zones": [{"id": z, "label": ZONE_LABELS[z]} for z in ZONE_LABELS],
        "meta": {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tsLocal": datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S"),
            "source": source, "counts": counts,
        },
    }


# ------------------------------------------------------------------- mock

def collect_mock():
    nodes, edges = _skeleton()
    for n in nodes:
        n["status"] = MOCK_STATUS.get(n["id"], "unknown")
    return _finalize(nodes, edges, "snapshot 2026-11-05 (mock)")


# -------------------------------------------------------------------- mcp

class MCP:
    """Minimal MCP streamable-HTTP (JSON-RPC) client for tools/call.
    If your MCP uses a different transport/auth, this is the only place to
    adjust (see _post / headers)."""

    def __init__(self, url, token, prefix=""):
        self.url = url.rstrip("/")
        self.token = token
        self.prefix = prefix           # e.g. "" or "IT_Infra."
        self.sid = None
        self._ready = False

    def _headers(self):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        return h

    def _post(self, payload):
        r = requests.post(self.url, headers=self._headers(), json=payload,
                          timeout=30, stream=True)
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            self.sid = sid
        if r.status_code >= 400:
            raise RuntimeError(f"MCP HTTP {r.status_code}: {r.text[:200]}")
        ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            data = None
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except Exception:
                        pass
            return data
        if not r.content:
            return None
        return r.json()

    def ensure(self):
        if self._ready:
            return
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "capabilities": {},
                               "clientInfo": {"name": "netmap", "version": "1.0"}}})
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:
            pass
        self._ready = True

    def call(self, name, args=None):
        """Call a tool, return its parsed JSON result (the tool's dict)."""
        self.ensure()
        res = self._post({"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                          "method": "tools/call",
                          "params": {"name": self.prefix + name,
                                     "arguments": args or {}}})
        if not res or "result" not in res:
            raise RuntimeError(f"no result for {name}: {str(res)[:200]}")
        content = res["result"].get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except Exception:
                    return {"_text": block["text"]}
        sc = res["result"].get("structuredContent")
        return sc if sc is not None else {}


def _mark(nodes_by_id, nid, status):
    if nid in nodes_by_id:
        nodes_by_id[nid]["status"] = status


def collect_mcp():
    url = os.environ.get("MCP_URL", "https://mcp.21sunpassion.com/mcp")
    token = os.environ.get("MCP_TOKEN", "")
    prefix = os.environ.get("MCP_TOOL_PREFIX", "")   # try "IT_Infra." if bare names 404
    mcp = MCP(url, token, prefix)

    nodes, edges = _skeleton()
    bid = {n["id"]: n for n in nodes}

    # FortiGate reachable -> fw/vlans/bridge up
    try:
        st = mcp.call("fortigate_status")
        if st.get("serial") or st.get("version"):
            for k in ("FGT", "BRIDGE2", "V2", "V3", "V4", "V5", "V9", "V10", "V90", "V99"):
                _mark(bid, k, "up")
    except Exception:
        pass

    # WAN links
    try:
        ifs = mcp.call("fortigate_interfaces").get("interfaces", [])
        link = {i.get("name"): i.get("link") for i in ifs}
        _mark(bid, "WAN1", "up" if link.get("port1") else "down")
        _mark(bid, "WAN2", "up" if link.get("port15") else "down")
        _mark(bid, "WAN3", "up" if link.get("port16") else "down")
        if any(link.values()):
            _mark(bid, "INTERNET", "up")
    except Exception:
        pass

    # IPsec tunnels -> sites + azure gateway
    tmap = {"FG-to-Kitchen C": "KITCHEN", "to-iNET": "INET",
            "FG-to-MT-99-211": "HOME", "VPN-Azure-HQ": "AZVPN",
            "IPsec to BS": "BS", "VMSupport": "VMSUP"}
    try:
        tuns = mcp.call("fortigate_ipsec_tunnels").get("tunnels", [])
        for t in tuns:
            nid = tmap.get(t.get("name"))
            if nid:
                _mark(bid, nid, "up" if t.get("phase2_up") else "down")
        if bid.get("AZVPN", {}).get("status") == "up":
            _mark(bid, "HUB", "up")
    except Exception:
        pass

    # Meraki APs
    apmap = {"AP-01": "AP01", "AP-02": "AP02", "AP-03": "AP03",
             "AP-04": "AP04", "AP-05": "AP05", "AP-06 (TEMP)": "AP06"}
    try:
        devs = mcp.call("meraki_device_statuses").get("devices", [])
        for d in devs:
            nid = apmap.get(d.get("name"))
            if nid:
                s = d.get("status")
                _mark(bid, nid, "up" if s == "online" else
                      ("warn" if s == "dormant" else "down"))
    except Exception:
        pass

    # Cisco switch reachable
    try:
        cs = mcp.call("cisco_status")
        if cs.get("show system") or cs.get("show version"):
            _mark(bid, "SW01", "up")
    except Exception:
        pass

    # Proxmox host (pve01) + guests.
    # NOTE: listing guests needs the API token to have PVEAuditor on '/'.
    #       Without it, proxmox_nodes still reports the host up/down, but
    #       proxmox_vms returns empty -> guests stay "unknown".
    try:
        pn = mcp.call("proxmox_nodes").get("nodes", [])
        online = any(n.get("node") == "pve01" and n.get("status") == "online"
                     for n in pn)
        _mark(bid, "PVE", "up" if online else "down")
    except Exception:
        pass
    # best-effort name match for the known guests on pve01
    guest_names = {"AD01": "ADSRV", "ARC": "NASVM", "NAS": "NASVM",
                   "XPENOLOGY": "NASVM", "DSM": "NASVM",
                   "FORTIMANAGER": "FMG", "FMG": "FMG", "VM107": "FMG", "107": "FMG"}
    try:
        vms = mcp.call("proxmox_vms").get("vms", [])
        for v in vms:
            nm = str(v.get("name") or "").upper()
            vid = str(v.get("vmid") or "")
            st = str(v.get("status") or "").lower()
            hit = None
            for key, nid in guest_names.items():
                if key in nm or key == vid:
                    hit = nid
                    break
            if hit:
                _mark(bid, hit, "up" if st == "running" else "warn")
    except Exception:
        pass

    # Azure VMs power state
    vmmap = {"vm-sunsu-bi": "VMBI", "sap-b1-app": "SAPAPP", "sap-b1-db": "SAPDB"}
    try:
        azvms = mcp.call("azure_vms").get("vms", [])
        for v in azvms:
            nid = vmmap.get(v.get("name"))
            if nid:
                p = (v.get("powerState") or "").lower()
                _mark(bid, nid, "up" if "running" in p else "warn")
    except Exception:
        pass

    # Azure SQL MI + BI/SAP spoke rollup
    try:
        sql = mcp.call("azure_sql")
        for mi in sql.get("managedInstances", []):
            if mi.get("name") == "dwhbi":
                _mark(bid, "DWHBI", "up" if mi.get("state") == "Ready" else "warn")
    except Exception:
        pass
    for spoke, kids in (("BI", ("DWHBI", "VMBI")), ("SAP", ("SAPAPP", "SAPDB"))):
        if any(bid.get(k, {}).get("status") == "up" for k in kids):
            _mark(bid, spoke, "up")
        elif all(bid.get(k, {}).get("status") in ("warn", "down") for k in kids):
            _mark(bid, spoke, "warn")

    # FortiGate-side services: up if the firewall is up
    if bid.get("FGT", {}).get("status") == "up":
        for k in ("SSLVPN", "L2TP"):
            if bid[k]["status"] == "unknown":
                _mark(bid, k, "up")

    return _finalize(nodes, edges, f"live via MCP ({url})")


def collect():
    mode = os.environ.get("COLLECTOR", "mock").lower()
    if mode == "mcp":
        try:
            return collect_mcp()
        except Exception as e:
            data = collect_mock()
            data["meta"]["source"] = f"MCP error, showing snapshot: {e}"
            return data
    return collect_mock()
