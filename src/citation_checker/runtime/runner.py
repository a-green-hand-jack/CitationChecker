from __future__ import annotations
import json, os, selectors, signal, subprocess, sys, time
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any
from .config import DEFAULT_MODEL, DEFAULT_PROVIDER
from .staging import stage_manuscript
from .trajectory import TrajectoryRecorder, redact
from .verify import verify_report
SYSTEM_PROMPT = "You are CitationChecker. Use the registered SDK tools and submit both mechanically valid reports."
def _run_id(manuscript: Path) -> str:
    stamp=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()); stem="".join(c if c.isalnum() or c in "-_" else "-" for c in manuscript.stem)[:48]; return f"{stamp}-{stem}"
def _kill_process_group(proc: subprocess.Popen) -> None:
    try: os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError: return
    try: proc.wait(timeout=1)
    except subprocess.TimeoutExpired: pass
    try: os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError: pass
def _write_json(path: Path, payload: dict[str,Any]) -> None: path.write_text(json.dumps(redact(payload),indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def _capture(proc: subprocess.Popen, recorder: TrajectoryRecorder, response: Path, timeout: int) -> bool:
    deadline=time.monotonic()+timeout; timed_out=False; buffer=b""; assert proc.stdout is not None
    with selectors.DefaultSelector() as selector, response.open("w",encoding="utf-8") as log:
        selector.register(proc.stdout,selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic()>=deadline and not timed_out: timed_out=True; _kill_process_group(proc)
            for key,_ in selector.select(timeout=.2):
                chunk=os.read(key.fd,65536)
                if not chunk: selector.unregister(key.fileobj); break
                buffer+=chunk
                while b"\n" in buffer:
                    line,buffer=buffer.split(b"\n",1); text=line.decode("utf-8",errors="replace"); log.write(redact(text)+"\n"); log.flush(); recorder.record_line(text)
        if buffer:
            text=buffer.decode("utf-8",errors="replace"); log.write(redact(text)+"\n"); recorder.record_line(text)
    proc.wait(); return timed_out
def run_check(manuscript:Path, *, out:Path|None, provider:str|None, model:str|None, thinking:str|None, timeout:int, dry_run:bool, max_steps:int=12, max_tokens:int|None=80000, disable_paper_search:bool=False, max_output_tokens:int=4096)->int:
    del thinking
    provider,model=provider or DEFAULT_PROVIDER, model or DEFAULT_MODEL; package=Path(__file__).resolve().parents[1]; run_root=Path(os.environ.get("CITATIONCHECKER_RUN_ROOT","runs")).resolve(); run_dir=out.resolve() if out else run_root/_run_id(manuscript)
    if run_dir.exists(): print(f"Refusing to overwrite existing run: {run_dir}"); return 2
    try: sdk_version = package_version("openai")
    except Exception: sdk_version = "missing"
    receipt={"schema_version":3,"agent_backend":"openai-sdk","sdk_version":sdk_version,"provider":provider,"model":model,"max_steps":max_steps,"max_tokens":max_tokens,"max_output_tokens":max_output_tokens,"timeout_seconds":timeout,"paper_search_enabled":not disable_paper_search,"exit_code":None,"runner_exit_code":2,"verified":False,"verify_errors":[],"stop_reason":"setup_error","secrets_redacted":True,"usage_scope":"OpenAI SDK model requests only; external CLI usage excluded"}
    recorder=None; proc=None; started=time.monotonic(); code=2
    try:
        if min(timeout,max_steps,max_output_tokens)<1 or (max_tokens is not None and max_tokens<0): raise ValueError("Budgets must be positive; max_tokens=0 disables only the cumulative token cap")
        stage_manuscript(manuscript,run_dir,package); prompt="Audit ./input. Inspect the manifest and source, register every citation-context ID, and submit both reports using write_report."
        _write_json(run_dir/"task.json",{**receipt,"prompt":prompt,"tools":["inspect_workspace","verify_references","write_report"]+([] if disable_paper_search else ["retrieve_paper"])})
        print(f"run directory: {run_dir}",flush=True)
        if dry_run: receipt["stop_reason"],code="dry_run",0
        else:
            recorder=TrajectoryRecorder(run_dir/"trajectory.jsonl",SYSTEM_PROMPT); env={**os.environ,"CITATIONCHECKER_RUN_DIR":str(run_dir),"CITATIONCHECKER_PYTHON":sys.executable,"CITATIONCHECKER_PROVIDER":provider,"CITATIONCHECKER_MODEL":model,"CITATIONCHECKER_MAX_STEPS":str(max_steps),"CITATIONCHECKER_MAX_TOKENS":"none" if max_tokens is None or max_tokens==0 else str(max_tokens),"CITATIONCHECKER_MAX_OUTPUT_TOKENS":str(max_output_tokens),"CITATIONCHECKER_ENABLE_PAPER_SEARCH":"0" if disable_paper_search else "1"}
            if provider in {"apex", "gpt-priority"} and env.get("APEX_GPT_API_KEY"):
                env.setdefault("OPENAI_API_KEY", env["APEX_GPT_API_KEY"])
            proc=subprocess.Popen([sys.executable,"-m","citation_checker.runtime.sdk_worker"],cwd=run_dir/"workspace",env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            timed_out=_capture(proc,recorder,run_dir/"response.txt",timeout); receipt["exit_code"]=proc.returncode; state=json.loads((run_dir/"state.json").read_text()) if (run_dir/"state.json").exists() else {}; report=run_dir/"workspace/output/citation-report.md"; ok,errors,data=verify_report(report); expected=state.get("pending_citation_ids",[])+state.get("processed_citation_ids",[]); actual=[x.get("citation") for x in (data or {}).get("citations",[]) if isinstance(x,dict)]; aliases=state.get("citation_aliases",{}); coverage=bool(state.get("registered")) and sorted([aliases.get(x,x) for x in actual])==sorted(expected);
            if not coverage: errors.append("report does not cover registered citation IDs")
            ok=ok and coverage and state.get("report_verified",False)
            if timed_out: reason,code="timeout",124
            elif state.get("stop_reason"):
                reason=state["stop_reason"]
                code=0 if reason=="completed" else (1 if reason=="provider_error" else 2)
            elif proc.returncode: reason,code="provider_error",1
            elif not ok: reason,code="invalid_report",2
            else: reason,code="completed",0
            receipt.update(verified=ok,verify_errors=errors,stop_reason=reason,state_summary=state,trajectory_summary=recorder.summary(),report=str(report),trajectory=str(recorder.path))
    except KeyboardInterrupt: receipt["stop_reason"],code="interrupted",130
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc: receipt["error"]=f"{type(exc).__name__}: {exc}"; code=2
    finally:
        if proc is not None and proc.poll() is None: _kill_process_group(proc)
        receipt["elapsed_seconds"]=round(time.monotonic()-started,3); receipt["runner_exit_code"]=code
        if recorder: recorder.record_stop(receipt["stop_reason"],exit_code=receipt["exit_code"],elapsed_seconds=receipt["elapsed_seconds"]); recorder.close()
        run_dir.mkdir(parents=True,exist_ok=True); _write_json(run_dir/"receipt.json",receipt)
    print(f"stop: {receipt['stop_reason']}; receipt: {run_dir/'receipt.json'}",flush=True); return code
