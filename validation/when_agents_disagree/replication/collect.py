#!/usr/bin/env python3
"""Collector for the When-Agents-Disagree conceptual replication.

Design fixed BEFORE any data was collected (see README.md beside this file):
HotpotQA distractor setting, ReAct agent with Search/Retrieve/Finish over the
item's own ten paragraphs, temperature 0.7, ten identical runs per
(model, item). Stdlib only; resumable; hard cost cap.

Usage:
  collect.py --phase pilot --cap-usd 3.00
  collect.py --phase main  --cap-usd 27.00 --models m1,m2,m3,m4
  collect.py --self-test
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRATCH = REPO / "scratch" / "wad_replication"
DATASET = SCRATCH / "hotpot_dev_distractor_v1.json"
RUNS = SCRATCH / "runs"

SELECTION_SEED_TAG = "wad-replication-v1"
PILOT_N = 20
MAIN_N = 200
DRAWS = 10
TEMPERATURE = 0.7
MAX_STEPS = 8
MAX_TOKENS_PER_CALL = 384
TIMEOUT_S = 90
RETRIES = 5
# concurrent episodes per model; an episode holds at most one in-flight
# request, so this bounds per-model concurrency (endpoint limit: 200/model).
# Models run in parallel with each other on top of this.
WORKERS = 100

PILOT_MODELS = [
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen3-32B",
    "google/gemma-3-27b-it",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "microsoft/phi-4",
    "mistralai/Mistral-Small-24B-Instruct-2501",
]

# USD per 1M tokens (input, output), deepinfra.com/pricing as of 2026-08-01;
# used for the cap and estimates only, actual usage tokens are recorded
PRICES = {
    "Qwen/Qwen2.5-72B-Instruct": (0.36, 0.40),
    "Qwen/Qwen3-32B": (0.08, 0.28),
    "google/gemma-3-27b-it": (0.08, 0.16),
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": (0.10, 0.32),
    "microsoft/phi-4": (0.07, 0.14),
    "mistralai/Mistral-Small-24B-Instruct-2501": (0.05, 0.08),
}

SYSTEM_PROMPT = """You are answering a multi-hop question using a small document collection.
You interact in strict turns. In each turn output exactly one Thought line and one Action line:

Thought: <one sentence of reasoning>
Action: <one of the three actions below>

Actions:
  Search[<keywords>]   - returns document titles ranked by keyword match
  Retrieve[<title>]    - returns the full text of the titled document
  Finish[<answer>]     - ends the episode with your final answer

Rules: answer with a short span (a name, date, phrase, or yes/no), not a
sentence. Use Finish[...] as soon as you know the answer. Output nothing after
the Action line."""

_ACTION_RE = re.compile(
    r"Action:\s*(Search|Retrieve|Finish)\s*\[(.*?)\]", re.DOTALL
)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.casefold())


def search_titles(query: str, titles: list[str]) -> str:
    """Deterministic keyword match: score = overlap of query tokens with title
    tokens; ties broken by title order in the item (stable)."""
    q = set(_tokens(query))
    scored = []
    for pos, title in enumerate(titles):
        score = len(q & set(_tokens(title)))
        if score > 0:
            scored.append((-score, pos, title))
    scored.sort()
    if not scored:
        return (
            "No titles matched. Available titles: "
            + "; ".join(titles)
        )
    return "Matching titles: " + "; ".join(t for _, _, t in scored[:5])


def retrieve_text(title: str, context: list) -> str:
    """Exact case-insensitive title match first, then containment fallback."""
    want = title.casefold().strip()
    for name, sentences in context:
        if name.casefold() == want:
            return "".join(sentences)
    for name, sentences in context:
        if want and (want in name.casefold() or name.casefold() in want):
            return f"(closest title: {name}) " + "".join(sentences)
    return (
        "No such title. Available titles: "
        + "; ".join(name for name, _ in context)
    )


def parse_action(reply: str) -> tuple[str, str] | None:
    """The LAST well-formed action in the reply wins (models sometimes restate
    the format before acting); <think> blocks are stripped first."""
    cleaned = _THINK_RE.sub("", reply)
    matches = list(_ACTION_RE.finditer(cleaned))
    if not matches:
        return None
    m = matches[-1]
    # models often quote the argument; the quotes are never part of it
    return m.group(1), m.group(2).strip().strip("\"'").strip()


class CostMeter:
    """Thread-safe accumulated spend with a hard cap. State persisted so
    resumed runs keep counting from the true total."""

    def __init__(self, state_path: Path, cap_usd: float):
        self.path = state_path
        self.cap = cap_usd
        self.lock = threading.Lock()
        self.spent = 0.0
        self.calls = 0
        if state_path.is_file():
            st = json.loads(state_path.read_text())
            self.spent = st["spent_usd"]
            self.calls = st["calls"]

    def add(self, model: str, tokens_in: int, tokens_out: int) -> None:
        p_in, p_out = PRICES[model]
        cost = tokens_in * p_in / 1e6 + tokens_out * p_out / 1e6
        with self.lock:
            self.spent += cost
            self.calls += 1
            if self.calls % 50 == 0:
                self._flush()
            if self.spent > self.cap:
                self._flush()
                raise RuntimeError(
                    f"COST CAP HIT: ${self.spent:.2f} > ${self.cap:.2f}; "
                    "collection aborted (resumable)"
                )

    def _flush(self) -> None:
        self.path.write_text(
            json.dumps({"spent_usd": round(self.spent, 6), "calls": self.calls})
        )

    def flush(self) -> None:
        with self.lock:
            self._flush()


def _api_key() -> str:
    cfg = json.loads(
        (Path.home() / "Spaghetti-Architect" / "bench" / "config.json").read_text()
    )
    key = cfg.get("api_key", "")
    if not key:
        raise SystemExit("no api_key in the bench config")
    return key


def chat(model: str, messages: list[dict], key: str, meter: CostMeter) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS_PER_CALL,
        }
    ).encode()
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                "https://api.deepinfra.com/v1/openai/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                out = json.load(r)
            usage = out.get("usage", {})
            meter.add(
                model,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            )
            return out["choices"][0]["message"]["content"] or ""
        except RuntimeError:
            raise  # the cap; never retried
        except Exception as exc:  # transient network/5xx/429
            last = exc
            time.sleep(2.0 * (2**attempt) + random.random())
    raise ConnectionError(f"exhausted retries: {last!r}")


def run_episode(
    model: str,
    item: dict,
    draw: int,
    key: str,
    meter: CostMeter,
    stopped: threading.Event,
) -> dict:
    if stopped.is_set():
        raise RuntimeError("stopped: cost cap reached")
    titles = [name for name, _ in item["context"]]
    system = SYSTEM_PROMPT
    if model == "Qwen/Qwen3-32B":
        system += "\n/no_think"  # Qwen3's documented soft switch; see README
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Question: {item['question']}"},
    ]
    actions: list[str] = []
    final_answer = ""
    status = "no_finish"
    for _step in range(MAX_STEPS):
        if stopped.is_set():
            raise RuntimeError("stopped: cost cap reached")
        reply = chat(model, messages, key, meter)
        messages.append({"role": "assistant", "content": reply})
        parsed = parse_action(reply)
        if parsed is None:
            obs = (
                "Your reply had no valid Action line. Reply with exactly one "
                "'Thought:' line and one 'Action:' line."
            )
            actions.append("MALFORMED")
        else:
            kind, arg = parsed
            actions.append(f"{kind}[{arg}]")
            if kind == "Finish":
                final_answer = arg
                status = "finished"
                break
            obs = (
                search_titles(arg, titles)
                if kind == "Search"
                else retrieve_text(arg, item["context"])
            )
        messages.append({"role": "user", "content": f"Observation: {obs}"})
    return {
        "model": model,
        "item_id": item["_id"],
        "draw": draw,
        "status": status,
        "final_answer": final_answer,
        "n_steps": len(actions),
        "actions": actions,
        "gold": item["answer"],
        "level": item["level"],
        "type": item["type"],
    }


def select_items(dataset: list[dict]) -> tuple[list[dict], list[dict]]:
    """Deterministic disjoint pilot/main selection, seeded from the tag."""
    by_id = sorted(dataset, key=lambda d: d["_id"])
    seed = int.from_bytes(
        hashlib.sha256(SELECTION_SEED_TAG.encode()).digest()[:8], "big"
    )
    picked = random.Random(seed).sample(by_id, PILOT_N + MAIN_N)
    return picked[:PILOT_N], picked[PILOT_N:]


def existing_keys(out_path: Path) -> set[tuple[str, str, int]]:
    done = set()
    if out_path.is_file():
        with gzip.open(out_path, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["status"] in ("finished", "no_finish"):
                    done.add((r["model"], r["item_id"], r["draw"]))
    return done


def _collect_model(
    model: str,
    items: list[dict],
    outdir: Path,
    key: str,
    meter: CostMeter,
    stopped: threading.Event,
) -> None:
    out_path = outdir / f"{model.replace('/', '__')}.jsonl.gz"
    done = existing_keys(out_path)
    todo = [
        (item, d)
        for item in items
        for d in range(DRAWS)
        if (model, item["_id"], d) not in done
    ]
    print(f"{model}: {len(done)} done, {len(todo)} to run", flush=True)
    if not todo:
        return
    failures = 0
    write_lock = threading.Lock()
    with gzip.open(out_path, "at", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {
                pool.submit(run_episode, model, item, d, key, meter, stopped): (
                    item["_id"],
                    d,
                )
                for item, d in todo
            }
            for n, fut in enumerate(as_completed(futures), 1):
                try:
                    rec = fut.result()
                except RuntimeError:
                    # the cap: stop every model's in-flight episodes at their
                    # next step, cancel this model's queue, spend nothing more
                    stopped.set()
                    pool.shutdown(wait=False, cancel_futures=True)
                    print(f"{model}: cost cap hit; stopping", flush=True)
                    return
                except ConnectionError as exc:
                    iid, d = futures[fut]
                    rec = {
                        "model": model,
                        "item_id": iid,
                        "draw": d,
                        "status": "stub",
                        "error": str(exc)[:200],
                    }
                    failures += 1
                with write_lock:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if n % 200 == 0:
                        fh.flush()
                        print(
                            f"  {model.split('/')[-1]}: {n}/{len(todo)} "
                            f"(total ${meter.spent:.2f})",
                            flush=True,
                        )
    print(f"{model}: complete, {failures} stubs", flush=True)


def collect(phase: str, models: list[str], cap_usd: float) -> None:
    dataset = json.loads(DATASET.read_text())
    pilot, main = select_items(dataset)
    items = pilot if phase == "pilot" else main
    outdir = RUNS / phase
    outdir.mkdir(parents=True, exist_ok=True)
    key = _api_key()
    meter = CostMeter(outdir / "cost_state.json", cap_usd)
    stopped = threading.Event()

    # each model gets its own episode pool (per-model endpoint limits are
    # independent), so models run fully in parallel
    with ThreadPoolExecutor(max_workers=len(models)) as models_pool:
        model_futs = [
            models_pool.submit(
                _collect_model, model, items, outdir, key, meter, stopped
            )
            for model in models
        ]
        for fut in as_completed(model_futs):
            fut.result()  # surface unexpected errors
    meter.flush()
    print(f"phase {phase} done: ${meter.spent:.2f}, {meter.calls} calls")
    if stopped.is_set():
        raise SystemExit(3)


def self_test() -> None:
    item = {
        "_id": "x1",
        "question": "Which city hosts the university founded by Ada Lovelace?",
        "answer": "Springfield",
        "level": "medium",
        "type": "bridge",
        "context": [
            ["Ada Lovelace", ["Ada Lovelace founded Example University. "]],
            ["Example University", ["Example University is in Springfield. "]],
            ["Distractor College", ["Distractor College is elsewhere. "]],
        ],
    }
    titles = [n for n, _ in item["context"]]
    out = search_titles("Ada Lovelace university", titles)
    assert out.startswith("Matching titles: Ada Lovelace"), out
    assert "Example University" in out
    assert "No titles matched" in search_titles("zzz", titles)
    assert "Springfield" in retrieve_text("example university", item["context"])
    assert "No such title" in retrieve_text("qqq", item["context"])
    assert parse_action("Thought: t\nAction: Search[foo bar]") == ("Search", "foo bar")
    assert parse_action("<think>Action: Finish[x]</think>Action: Retrieve[T]") == (
        "Retrieve",
        "T",
    )
    assert parse_action("Action: Search[a]\nAction: Finish[b]") == ("Finish", "b")
    assert parse_action("no action here") is None
    ds = [{"_id": f"i{j:04d}"} for j in range(7405)]
    p1, m1 = select_items(ds)
    p2, m2 = select_items(ds)
    assert p1 == p2 and m1 == m2, "selection must be deterministic"
    assert len(p1) == PILOT_N and len(m1) == MAIN_N
    assert not {d["_id"] for d in p1} & {d["_id"] for d in m1}, "must be disjoint"
    print("self-test OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["pilot", "main"])
    ap.add_argument("--cap-usd", type=float, default=3.0)
    ap.add_argument("--models", type=str, default=",".join(PILOT_MODELS))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.phase:
        ap.error("--phase required (or --self-test)")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in models if m not in PRICES]
    if unknown:
        ap.error(f"no price entry for {unknown}; refusing to run uncapped")
    collect(args.phase, models, args.cap_usd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
