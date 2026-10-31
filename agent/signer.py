import requests

class SignerClient:
    def __init__(self,base_url,token):
        self.base_url=base_url.rstrip("/")
        self.token=token
        self.s=requests.Session()

    @property
    def configured(self):
        return bool(self.base_url and self.token)

    def _headers(self):
        return {"X-Signer-Token":self.token,"Content-Type":"application/json"}

    def _get(self,path,params=None,timeout=15):
        if not self.configured:
            raise RuntimeError("Signer is not configured")
        r=self.s.get(self.base_url+path,headers=self._headers(),params=params,timeout=timeout)
        body=None
        try: body=r.json()
        except Exception: body={"raw":r.text[:1200]}
        if r.status_code!=200:
            raise RuntimeError(f"SIGNER_GET_{r.status_code}:{body}")
        return body

    def _post(self,path,payload,timeout=25):
        if not self.configured:
            raise RuntimeError("Signer is not configured")
        r=self.s.post(self.base_url+path,headers=self._headers(),json=payload,timeout=timeout)
        body=None
        try: body=r.json()
        except Exception: body={"raw":r.text[:1600]}
        if r.status_code!=200:
            raise RuntimeError(f"SIGNER_POST_{r.status_code}:{body}")
        return body

    def health(self):
        if not self.configured:
            return {"ok":False,"configured":False,"error":"HL_SIGNER_TOKEN missing"}
        try:
            body=self._get("/health")
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

    def risk(self):
        return self._get("/risk")

    def snapshot(self):
        return self._get("/agent_snapshot",timeout=20)

    def fills(self,coin="BTC",limit=50):
        return self._get("/fills",params={"coin":coin,"limit":limit},timeout=20)

    def place_bracket(self,coin,is_buy,size,entry_price,stop_loss,take_profit):
        return self._post("/place_bracket_order",{
            "coin":coin,"is_buy":bool(is_buy),"size":float(size),
            "entry_price":float(entry_price),"stop_loss":float(stop_loss),
            "take_profit":float(take_profit)
        },timeout=30)

    def close_testnet_position(self,coin):
        return self._post("/close_testnet_position",{"coin":coin},timeout=30)
