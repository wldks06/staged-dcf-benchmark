"""Run an open-weight model on a question set with vLLM. Never overwrites, never deletes.

    python run_model.py --preset qwen3-32b \
        --qa ../data/questions/QA_set_v2.json,../data/questions/QA_set_ver03.json,../data/questions/QA_set_ver03_newco.json \
        --levels 2,3,4,5 --tools none,calc --seeds 0,1,2 --tp 2 --out ../results/answers/qwen3-32b
    python run_model.py --preset fin-r1 --dry-run        # prompts only, no GPU

On the cluster this is called by slurm/run_model.sbatch (one job per model). Settings of the paper
(Section IV-D):
- Models: the twelve presets in MODELS below, each financial fine-tune next to the base it was trained from.
  Each model's recommended decoding; reasoning models are sampled under seeds 0, 1, 2 with up to 24,576 new
  tokens, the other models decode greedily once with up to 8,192 tokens.
- Prompts: the system prompt SYSTEM and the question text, built with the model's own chat template and
  passed as token ids (no double BOS).
- --tools calc: a calculator the model can call by writing <calc>EXPRESSION</calc>. Generation stops
  at </calc>, the expression is evaluated safely (numbers, + - * / ** ( ), sqrt, exp, log, abs,
  round, min, max), "<result>VALUE</result>" is appended and generation continues. The protocol is plain
  text, so every model gets the same tool regardless of its native tool format. Up to 300 calls per answer
  (--max-calc-rounds). A first pass allowed 60, too few for a full DCF done call by call, so the answers that
  hit that cap were rerun at 300 (make_capped_map.py, slurm/rerun_capped.sbatch); analyze_paper.py takes the
  later file for a question answered twice under the same setting.
- --seeds: one output file per seed. The seed of a question is a hash of (question id, seed), so it does
  not depend on --shard / --only / --exclude-qa.
- Reasoning text: for any model, the text before the last </think> is stored as `thinking` and the rest as
  `response`; only `response` is graded for final answers. A reasoning model that never closes </think> within
  the budget gets response "" and thinking_finished = False.
- Each record also stores the decoding settings, the seed, the tool calls and the vLLM version.

Compatibility notes for the V100 nodes (vLLM 0.10.1 with transformers 5), each with the job log that showed it
(logs/slurm/):
- vLLM 0.10.1 reads tokenizer.all_special_tokens_extended, which transformers 5 removed (smoke test 12259427).
  apply_compat_patches() adds that one read-only property back; it cannot change how text is tokenized.
- transformers 5 keeps rope_theta inside rope_scaling, and vLLM 0.10.1 reads config.rope_theta with a default
  of 10000 for Llama (500000 is right), so Llama-3.1 and Fino1 would run with wrong positions and no error
  (compat_check.py, job 12259555). The patch restores the transformers-4 form of the RoPE fields.
- vLLM's custom all-reduce kernel fails on PCIe V100s without peer-to-peer access (12259593) and on one 2xH100
  node (12259979-12259981), so it is switched off for every multi-GPU job (NCCL instead, same results).
- The Triton prefix-prefill kernel does not compile on sm_70 (12259627), so with vLLM 0.10 prefix caching and
  chunked prefill are off.
- Weights are loaded from safetensors only (load_format="safetensors"); every model in this study has them.
Answer files are named answers_ver02_<preset>[_think][_calc]_s<seed>_<set>_L2345_<time>.jsonl (the answer
format has not changed since runner version 2, so the prefix is kept; each record names its runner).
"""
import argparse, ast, datetime, hashlib, json, math, operator, os, re, sys, time

SYSTEM = ("You are a careful financial analyst. Work step by step and show every "
          "intermediate number you compute, with its label and unit. Use only the numbers "
          "given in the question and data. End your reply with one line that starts with "
          "'FINAL ANSWER:' followed by the requested values and units.")

CALC_NOTE = ("\n\nYou have a calculator. To use it, write <calc>EXPRESSION</calc> and stop. "
             "EXPRESSION may contain only numbers, + - * / ** ( ) and sqrt(), exp(), log(), abs(), "
             "round(), min(), max(); no units, no % or $ signs, no thousands separators. "
             "The result comes back as <result>VALUE</result>, then you continue. "
             "Use the calculator for every multiplication, division, power and long sum.")

# Short names -> (Hugging Face id, reasoning model?, enable_thinking flag for the chat template,
#                 decoding). Decoding follows each model card; greedy for plain instruct models.
SAMPLED = dict(temperature=0.6, top_p=0.95, top_k=20)
R1 = dict(temperature=0.6, top_p=0.95)
GREEDY = dict(temperature=0.0)
MODELS = {
    # general-purpose baselines
    "qwen25-7b":  ("Qwen/Qwen2.5-7B-Instruct", False, None, GREEDY),
    "qwen25-32b": ("Qwen/Qwen2.5-32B-Instruct", False, None, GREEDY),
    "qwen3-8b":   ("Qwen/Qwen3-8B", True, True, SAMPLED),
    "qwen3-14b":  ("Qwen/Qwen3-14B", True, True, SAMPLED),
    "qwen3-32b":  ("Qwen/Qwen3-32B", True, True, SAMPLED),
    "llama31-8b": ("meta-llama/Llama-3.1-8B-Instruct", False, None, GREEDY),
    # financial LLMs, each paired with the base above it was fine-tuned from
    "fin-r1":      ("SUFE-AIFLM-Lab/Fin-R1", True, None, R1),            # Qwen2.5-7B-Instruct
    "dianjin-7b":  ("DianJin/DianJin-R1-7B", True, None, R1),            # Qwen2.5-7B-Instruct
    "dianjin-32b": ("DianJin/DianJin-R1-32B", True, None, R1),           # Qwen2.5-32B-Instruct
    "fin-o1-8b":   ("TheFinAI/Fin-o1-8B", True, True, SAMPLED),          # Qwen3-8B
    "fin-o1-14b":  ("TheFinAI/Fin-o1-14B", True, True, SAMPLED),         # Qwen3-14B
    "fino1-8b":    ("TheFinAI/Fino1-8B", True, None, R1),                # Llama-3.1-8B-Instruct
}


# ------------------------------------------------------------------ prompts (as in the pilot runner)
def load(path):
    d = json.load(open(path))
    if not all(k in d for k in ("questions", "rubric")):
        sys.exit(f"Expected keys 'questions' and 'rubric' in {path}, found {list(d)}")
    return d


def data_table(qid, rubric):
    lines = [r["criterion"] for r in rubric if r["question_id"] == qid and r.get("kind") == "input"]
    if not lines:
        return ""
    cleaned = [re.sub(r"^Pulls\s+", "", l) for l in lines]
    return ("\n\nData from the 10-K (use these figures; you do not need to look anything up):\n- "
            + "\n- ".join(cleaned))


def build_prompts(d, levels):
    out = []
    for q in d["questions"]:
        if int(q["level"]) not in levels:
            continue
        text = q["question"]
        if int(q["level"]) == 3:
            text += data_table(q["question_id"], d["rubric"])
        out.append({"question_id": q["question_id"], "level": int(q["level"]), "tier": q.get("tier", ""),
                    "prompt": text})
    return out


# ------------------------------------------------------------------ calculator
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Mod: operator.mod}
_FUN = {"sqrt": math.sqrt, "exp": math.exp, "log": math.log, "ln": math.log, "abs": abs, "round": round,
        "min": min, "max": max}


def _ev(n):
    if isinstance(n, ast.Expression):
        return _ev(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e12):
            raise ValueError("power too large")
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_ev(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUN and not n.keywords:
        return _FUN[n.func.id](*[_ev(a) for a in n.args])
    if isinstance(n, ast.Name) and n.id in ("pi", "e"):
        return math.pi if n.id == "pi" else math.e
    raise ValueError("not allowed: " + type(n).__name__)


def calculate(expr):
    s = expr.strip().replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)          # 1,234.5 -> 1234.5
    s = s.replace("$", "")
    if len(s) > 400:
        return "error: expression too long"
    try:
        v = _ev(ast.parse(s, mode="eval"))
        return f"{v:.10g}"
    except Exception as e:  # noqa: BLE001 - any failure is reported back to the model
        return f"error: {str(e)[:60]}"


# ------------------------------------------------------------------ helpers
def qseed(qid, seed):
    return int(hashlib.sha256(f"{qid}|{seed}".encode()).hexdigest()[:8], 16)


def split_thinking(text, reasoning, finished_budget):
    if "</think>" in text:
        cut = text.rfind("</think>")
        return text[cut + len("</think>"):].strip(), text[:cut].replace("<think>", "", 1).strip(), True
    if reasoning and (text.lstrip().startswith("<think>") or finished_budget):
        return "", text.replace("<think>", "", 1).strip(), False
    return text.strip(), "", None


def _restore_rope_fields(cfg):
    """transformers 5 keeps rope_theta inside rope_scaling / rope_parameters; vLLM 0.10.1 reads
    config.rope_theta (default 10000 for Llama, so Llama-3.1 would silently run with the wrong positions).
    Put the transformers-4 form back: rope_theta as its own field, rope_scaling without rope_theta and
    None when it only said 'default'. Returns what was changed."""
    changed = []
    for c in [cfg] + [getattr(cfg, k) for k in ("text_config",) if getattr(cfg, k, None) is not None]:
        params = getattr(c, "rope_parameters", None) or getattr(c, "rope_scaling", None)
        if not isinstance(params, dict):
            continue
        params = dict(params)
        theta = params.pop("rope_theta", None)
        if getattr(c, "rope_theta", None) is None and theta is not None:
            try:
                c.rope_theta = theta
            except AttributeError:
                c.__dict__["rope_theta"] = theta
            changed.append(f"rope_theta={theta}")
        new_scaling = None if set(params) <= {"rope_type"} and params.get("rope_type", "default") == "default" else params
        if getattr(c, "rope_scaling", None) != new_scaling:
            try:
                c.rope_scaling = new_scaling
            except AttributeError:
                c.__dict__["rope_scaling"] = new_scaling
            changed.append(f"rope_scaling={new_scaling}")
    return changed


def apply_compat_patches():
    """Compatibility patches for vLLM 0.10.1 under transformers 5 (the V100 nodes); see the module header.
    1. tokenizer.all_special_tokens_extended, removed in transformers 5, read by vLLM's tokenizer wrapper.
    2. RoPE fields of the model config (_restore_rope_fields), applied to every config vLLM loads.
    Both are no-ops when the attribute already exists / the fields are already in the old form."""
    applied = []
    try:
        from transformers.tokenization_utils_base import PreTrainedTokenizerBase
    except ImportError:
        return applied
    if "all_special_tokens_extended" not in dir(PreTrainedTokenizerBase):
        PreTrainedTokenizerBase.all_special_tokens_extended = property(lambda self: list(self.all_special_tokens))
        applied.append("PreTrainedTokenizerBase.all_special_tokens_extended")
    try:
        import vllm
        import vllm.transformers_utils.config as vtc
    except ImportError:
        return applied
    if vllm.__version__.startswith("0.10.") and not getattr(vtc.get_config, "_ver03_patched", False):
        orig = vtc.get_config

        def get_config_compat(*args, **kwargs):
            cfg = orig(*args, **kwargs)
            ch = _restore_rope_fields(cfg)
            if ch:
                print(f"[compat] {type(cfg).__name__}: restored {', '.join(ch)}", flush=True)
            return cfg
        get_config_compat._ver03_patched = True
        vtc.get_config = get_config_compat
        import importlib
        for modname in ("vllm.config", "vllm.engine.arg_utils"):     # modules that imported get_config by name
            try:
                mod = importlib.import_module(modname)
                if getattr(mod, "get_config", None) is orig:
                    mod.get_config = get_config_compat
            except ImportError:
                pass
        applied.append("vllm get_config -> RoPE fields restored")
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default="../data/questions/QA_set_v2.json")
    ap.add_argument("--preset", choices=sorted(MODELS), help="short model name (see MODELS)")
    ap.add_argument("--model", help="any Hugging Face id instead of --preset")
    ap.add_argument("--reasoning", action="store_true", help="with --model: treat as a reasoning model")
    ap.add_argument("--levels", default="2,3,4,5")
    ap.add_argument("--only", default="")
    ap.add_argument("--exclude-qa", default="")
    ap.add_argument("--shard", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tools", default="none", help="comma list: none, calc")
    ap.add_argument("--seeds", default="0", help="comma list; one output file per seed (greedy models: use 0)")
    ap.add_argument("--max-new-tokens", type=int, default=0, help="0 = 24576 for reasoning models, 8192 otherwise")
    ap.add_argument("--max-model-len", type=int, default=32768)
    ap.add_argument("--max-calc-rounds", type=int, default=300,
                    help="calculator calls allowed per answer. 60 in the first pass; a full DCF needs more "
                         "(Qwen3-14B hit 60 on 182 of 268 full-DCF answers and left no final answer), so 300 in the paper")
    ap.add_argument("--only-map", default="", help="JSON file {qa_tag: {seed: [question ids]}}: rerun just those (per QA file and seed)")
    ap.add_argument("--tp", type=int, default=1, help="tensor parallel size (GPUs)")
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--dtype", default="bfloat16", help="bfloat16 on H100; float16 on V100 (no bfloat16 there)")
    ap.add_argument("--out", default="../results/answers")
    ap.add_argument("--label", default="", help="extra tag in the output file name")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.preset:
        hf_id, reasoning, think_flag, decoding = MODELS[a.preset]
        short = a.preset
    elif a.model:
        hf_id, reasoning, think_flag, decoding = a.model, a.reasoning, (True if a.reasoning else None), (R1 if a.reasoning else GREEDY)
        short = a.model.split("/")[-1]
    else:
        sys.exit("give --preset or --model")
    max_new = a.max_new_tokens or (24576 if reasoning else 8192)
    tools = [t.strip() for t in a.tools.split(",") if t.strip()]
    seeds = [int(s) for s in a.seeds.split(",")] if decoding.get("temperature", 0) > 0 else [0]

    jobs = []                                   # one entry per QA file (--qa takes a comma list)
    for qa_path in [x.strip() for x in a.qa.split(",") if x.strip()]:
        d = load(qa_path)
        prompts = build_prompts(d, {int(x) for x in a.levels.split(",")})
        if a.exclude_qa:
            skip = {q["question_id"] for q in json.load(open(a.exclude_qa))["questions"]}
            prompts = [p for p in prompts if p["question_id"] not in skip]
        if a.shard:
            k, n = (int(x) for x in a.shard.split("/"))
            prompts = prompts[k - 1::n]
        if a.only:
            keep = {x.strip() for x in a.only.split(",")}
            prompts = [p for p in prompts if p["question_id"] in keep]
        if a.limit:
            prompts = prompts[:a.limit]
        if prompts:
            jobs.append((os.path.splitext(os.path.basename(qa_path))[0].replace("QA_set_", ""), prompts))
    only_map = json.load(open(a.only_map)) if a.only_map else None
    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    lv = a.levels.replace(",", "")
    sh = ("_S" + a.shard.replace("/", "of")) if a.shard else ""
    if a.dry_run:
        for qa_tag, prompts in jobs:
            path = os.path.join(a.out, f"prompts_preview_ver02_{short}_{qa_tag}_L{lv}{sh}_{stamp}.txt")
            with open(path, "x") as f:
                for p in prompts:
                    f.write(f"===== {p['question_id']} (level {p['level']}) =====\nSYSTEM: {SYSTEM}\n"
                            f"[+ calculator note when --tools calc]\n{p['prompt']}\n\n")
            print(f"{len(prompts)} prompts for {hf_id} written to {path}. No model was run.")
        return

    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    import vllm
    patches = apply_compat_patches()
    print(f"compatibility patches applied: {patches or 'none needed'}", flush=True)
    tok = AutoTokenizer.from_pretrained(hf_id)
    # V100 nodes here are PCIe without peer-to-peer access: vLLM 0.10's custom all-reduce kernel fails during
    # CUDA-graph capture ("custom_all_reduce.cuh:453 invalid argument", smoke test 12259593); NCCL is used instead.
    # ... and the same kernel failed on 2 H100s of node g34 (custom_all_reduce.cuh:164, jobs 12259979-12259981),
    # so it is off for every multi-GPU job: NCCL all-reduce instead, same results, a little slower.
    no_car = a.tp > 1
    if no_car:
        patches.append("disable_custom_all_reduce (tp>1)")
    # vLLM 0.10 on V100 (sm_70): the Triton kernel used when a prompt reuses cached prefix blocks
    # (prefix_prefill.context_attention_fwd) does not compile ("PassManager::run failed", smoke test 12259627),
    # so prefix caching and chunked prefill, which both use it, are off there. Same answers, slower prefill.
    old_vllm = vllm.__version__.startswith("0.10.")
    extra = {}
    if old_vllm:
        extra["enable_chunked_prefill"] = False
        patches.append("prefix caching and chunked prefill off (vLLM 0.10, V100 Triton kernel)")
    llm = LLM(model=hf_id, tensor_parallel_size=a.tp, max_model_len=a.max_model_len,
              gpu_memory_utilization=a.gpu_mem, dtype=a.dtype, enable_prefix_caching=not old_vllm,
              trust_remote_code=False, seed=0, disable_custom_all_reduce=no_car, load_format="safetensors", **extra)
    print(f"Loaded {hf_id} (vLLM {vllm.__version__}, tp={a.tp}); questions {[(t, len(p)) for t, p in jobs]}; tools {tools}; seeds {seeds}", flush=True)

    def chat_ids(user_text, system):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user_text}]
        kw = {"enable_thinking": think_flag} if think_flag is not None else {}
        text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, **kw)
        return tok(text, add_special_tokens=False)["input_ids"]

    for tool in tools:
        system = SYSTEM + (CALC_NOTE if tool == "calc" else "")
        for seed in seeds:
            for qa_tag, prompts in jobs:
                if only_map is not None:
                    keep = set(only_map.get(qa_tag, {}).get(str(seed), []))
                    prompts = [p for p in prompts if p["question_id"] in keep]
                    if not prompts:
                        continue
                tag = f"{short}{'_think' if reasoning else ''}{'_calc' if tool == 'calc' else ''}_s{seed}{('_' + a.label) if a.label else ''}"
                path = os.path.join(a.out, f"answers_ver02_{tag}_{qa_tag}_L{lv}{sh}_{stamp}.jsonl")
                t0 = time.time()
                conv = []
                for p in prompts:
                    ids = chat_ids(p["prompt"], system)
                    conv.append(dict(p=p, base=ids, gen=[], text="", calls=[], done=False, rounds=0, finish=None))
                rnd = 0
                while True:
                    active = [c for c in conv if not c["done"]]
                    if not active:
                        break
                    reqs, params = [], []
                    for c in active:
                        ids = c["base"] + c["gen"]
                        budget = min(max_new - c.get("n_new", 0), a.max_model_len - len(ids) - 8)
                        if budget <= 16:
                            c["done"], c["finish"] = True, "length"
                            continue
                        sp = dict(max_tokens=budget, seed=qseed(c["p"]["question_id"], seed) + rnd)
                        sp.update({k: v for k, v in decoding.items()})
                        if tool == "calc":
                            sp.update(stop=["</calc>"], include_stop_str_in_output=True)
                        reqs.append(c); params.append(SamplingParams(**sp))
                    if not reqs:
                        break
                    outs = llm.generate([{"prompt_token_ids": c["base"] + c["gen"]} for c in reqs], params, use_tqdm=False)
                    for c, o in zip(reqs, outs):
                        out = o.outputs[0]
                        c["gen"] += list(out.token_ids)
                        c["text"] += out.text
                        c["n_new"] = c.get("n_new", 0) + len(out.token_ids)
                        c["finish"] = out.finish_reason
                        expr = None
                        if tool == "calc" and out.text.rstrip().endswith("</calc>") and "<calc>" in out.text:
                            body = out.text.rstrip()[:-len("</calc>")]
                            expr = body[body.rfind("<calc>") + len("<calc>"):]
                        if expr is not None and c["rounds"] < a.max_calc_rounds and c["n_new"] < max_new:
                            res = calculate(expr)
                            c["calls"].append([expr.strip()[:200], res])
                            add = f"\n<result>{res}</result>\n"
                            c["text"] += add
                            c["gen"] += tok(add, add_special_tokens=False)["input_ids"]
                            c["rounds"] += 1
                        else:
                            c["done"] = True
                    rnd += 1
                    if tool == "calc":
                        print(f"  [{tag}] round {rnd}: {sum(1 for c in conv if not c['done'])} questions still calling the calculator", flush=True)
                secs = round(time.time() - t0, 1)
                with open(path, "x") as f:
                    for c in conv:
                        resp, think, fin = split_thinking(c["text"], reasoning, c["finish"] == "length")
                        rec = dict(c["p"], model=hf_id, preset=short, response=resp, thinking=think,
                                   thinking_finished=fin, new_tokens=c.get("n_new", 0), max_new_tokens=max_new,
                                   finish_reason=c["finish"], decoding=decoding, seed=seed,
                                   question_seed=qseed(c["p"]["question_id"], seed), tools=tool,
                                   calc_calls=c["calls"], n_calc=len(c["calls"]), max_calc_rounds=a.max_calc_rounds, system=system,
                                   backend=f"vllm {vllm.__version__}", runner="run_model.py", compat_patches=patches, dtype=a.dtype, tp=a.tp, batch_seconds=secs,
                                   time=datetime.datetime.now().isoformat(timespec="seconds"))
                        f.write(json.dumps(rec) + "\n")
                n_len = sum(1 for c in conv if c["finish"] == "length")
                print(f"Finished {path}: {len(conv)} answers in {secs}s, {n_len} hit the token limit", flush=True)


if __name__ == "__main__":
    main()
