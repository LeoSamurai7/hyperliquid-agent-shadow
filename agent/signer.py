import requests

class SignerClient:
    def __init__(self,base_url,token):
        self.base_url=base_url.rstrip("/")
        self.token=token
        self.s=requests.Session()

    @property
    def configured(self):
        return bool(self.base_url and self.token)

    def health(self):
        if not self.configured:
            return {"ok":False,"configured":False,"error":"HL_SIGNER_TOKEN missing"}
        try:
            r=self.s.get(self.base_url+"/health",
                         headers={"X-Signer-Token":self.token},timeout=12)
            body=None
            try: body=r.json()
            except Exception: body={"raw":r.text[:500]}
            if r.status_code!=200:
                return {"ok":False,"configured":True,"status_code":r.status_code,"response":body}
            risk=(body or {}).get("risk_gate") or {}
            return {
                "ok":bool((body or {}).get("ok")),
                "configured":True,
                "network":(body or {}).get("network"),
                "market_data_network":(body or {}).get("market_data_network"),
                "execution_enabled":risk.get("execution_enabled"),
                "kill_switch":risk.get("kill_switch"),
                "agent_address":(body or {}).get("agent_address"),
                "account_address":(body or {}).get("account_address"),
                "risk_gate_version":risk.get("version")
            }
        except Exception as e:
            return {"ok":False,"configured":True,"error":f"{type(e).__name__}: {e}"}
