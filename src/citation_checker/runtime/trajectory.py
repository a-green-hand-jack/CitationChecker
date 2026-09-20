from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
_SECRET_KEY = re.compile(r"(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password|credential)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password)(\s*[:=]\s*)([\"']?)[^\s,\"'}]+\3")
def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = _SECRET_VALUE.sub(r"\1\2[REDACTED]", value)
        return re.sub(r"\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
    if isinstance(value, list): return [redact(x) for x in value]
    if isinstance(value, dict): return {k: "[REDACTED]" if _SECRET_KEY.search(str(k)) else redact(v) for k,v in value.items()}
    return value
class TrajectoryRecorder:
    def __init__(self, path: Path, system_prompt: str) -> None:
        self.path=path; path.parent.mkdir(parents=True, exist_ok=True); self.stream=path.open("w", encoding="utf-8"); self.sequence=0; self.events=0; self.protocol_errors=0; self.tool_counts={}; self.usage={"input":0,"output":0,"cache_read":0,"cache_write":0,"total":0}; self.write("system", {"role":"system","content":system_prompt})
    def write(self, kind: str, payload: dict[str,Any]) -> None:
        self.sequence += 1; record={"sequence":self.sequence,"timestamp":datetime.now(timezone.utc).isoformat(),"kind":kind,**payload}; self.stream.write(json.dumps(redact(record),ensure_ascii=False,sort_keys=True)+"\n"); self.stream.flush()
    def record_line(self,line: str) -> None:
        if not line.strip(): return
        try: event=json.loads(line)
        except json.JSONDecodeError as exc: self.protocol_errors+=1; self.write("protocol_error", {"raw":line.rstrip(),"error":str(exc)}); return
        if not isinstance(event,dict): self.protocol_errors+=1; self.write("protocol_error", {"raw":event,"error":"event was not a JSON object"}); return
        self.events+=1; kind=str(event.pop("kind","unknown")); self.write(kind,event)
        if kind=="tool_start":
            name=str(event.get("tool","unknown")); self.tool_counts[name]=self.tool_counts.get(name,0)+1
        usage=event.get("usage")
        if isinstance(usage,dict):
            for key in self.usage:
                if isinstance(usage.get(key),(int,float)): self.usage[key]+=int(usage[key])
    def record_state(self,state:dict[str,Any])->None: self.write("state_snapshot",{"state":state})
    def record_stop(self,reason:str,**details:Any)->None: self.write("stop",{"stop_reason":reason,**details})
    def summary(self)->dict[str,Any]: return {"events":self.events,"tool_counts":dict(sorted(self.tool_counts.items())),"usage":self.usage,"protocol_errors":self.protocol_errors,"secrets_redacted":True}
    def close(self)->None: self.stream.close()
