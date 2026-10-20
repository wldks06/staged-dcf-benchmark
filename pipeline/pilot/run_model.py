"""Run an open-source model on the Q&A set and save its answers.

Usage (on an IU GPU node):
    python run_model.py --qa QA_set_v1.json --model Qwen/Qwen2.5-7B-Instruct --limit 10
    python run_model.py --qa QA_set_v1.json --model Qwen/Qwen2.5-7B-Instruct
Check prompts without any model or GPU (safe on your Mac):
    python run_model.py --qa QA_set_v1.json --dry-run

What it does
- Reads QA_set_v1.json (read only).
- Default levels are 2 and 3. Level 1 asks the model to look numbers up in a 10-K,
  which a model with no tools and no filing cannot do, so it is skipped here.
- Level 3 questions get the needed 10-K figures attached as a data table
  (taken from the question's own rubric "input" items), so the test is the DCF itself.
- Writes one line per question to answers_<model>_<date-time>.jsonl. It never
  overwrites an earlier file and it never deletes anything.
"""
import argparse, json, os, sys, time, datetime, re

SYSTEM = ("You are a careful financial analyst. Work step by step and show every "
          "intermediate number you compute, with its label and unit. Use only the numbers "
          "given in the question and data. End your reply with one line that starts with "
          "'FINAL ANSWER:' followed by the requested values and units.")

def load(path):
    d = json.load(open(path))
    if not all(k in d for k in ("questions", "rubric")):
        sys.exit("Expected keys 'questions' and 'rubric' in %s, found %s" % (path, list(d)))
    return d

def data_table(qid, rubric):
    lines = [r["criterion"] for r in rubric
             if r["question_id"] == qid and r.get("kind") == "input"]
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
        out.append({"question_id": q["question_id"], "level": int(q["level"]), "prompt": text})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default="QA_set_v1.json")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--levels", default="2,3")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (0 = all)")
    ap.add_argument("--max-new-tokens", type=int, default=2048)
    ap.add_argument("--dry-run", action="store_true", help="write prompts only, no model")
    ap.add_argument("--thinking", action="store_true",
                    help="reasoning mode (Qwen3-style): model thinks inside <think>...</think> first; "
                         "uses the model card's recommended sampling (temp 0.6, top_p 0.95, top_k 20) with a fixed seed")
    ap.add_argument("--exclude-qa", default="", help="skip question IDs that appear in this QA file (e.g. QA_set_v1.json, already run)")
    ap.add_argument("--shard", default="", help="k/n: run only every n-th question starting at k (split one run across GPUs)")
    ap.add_argument("--only", default="", help="comma-separated question IDs to run (e.g. to finish a job that stopped early)")
    ap.add_argument("--check-template", action="store_true",
                    help="tokenizer-only check on the login node: show the end of the chat prompt, no model, no GPU")
    a = ap.parse_args()

    d = load(a.qa)
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
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    if a.dry_run:
        path = f"prompts_preview_{stamp}.txt"
        print("Questions selected:", len(prompts), " IDs:", ", ".join(p["question_id"] for p in prompts[:6]), "..." if len(prompts) > 6 else "")
        with open(path, "w") as f:
            for p in prompts:
                f.write(f"===== {p['question_id']} (level {p['level']}) =====\n{p['prompt']}\n\n")
        print(f"{len(prompts)} prompts written to {path}. No model was run.")
        return

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tmpl_kwargs = {"enable_thinking": bool(a.thinking)}   # ignored by templates that do not use it

    if a.check_template:
        tok = AutoTokenizer.from_pretrained(a.model)
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}]
        text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, **tmpl_kwargs)
        print("---- end of rendered prompt ----"); print(text[-200:])
        print("---- </think> token id:", tok.convert_tokens_to_ids("</think>"))
        return

    if not torch.cuda.is_available():
        sys.exit("No GPU visible. Run this inside a GPU job, not on the login node.")
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, device_map="auto")
    model.eval()

    tag = a.model.split("/")[-1] + ("_think" if a.thinking else "")
    lv = a.levels.replace(",", "")
    sh = ("_S" + a.shard.replace("/", "of")) if a.shard else ""
    qa = os.path.splitext(os.path.basename(a.qa))[0].replace("QA_set_", "")
    path = f"answers_{tag}_{qa}_L{lv}{sh}_{stamp}.jsonl"
    think_end = tok.convert_tokens_to_ids("</think>") if a.thinking else None
    print(f"Model {a.model} on {torch.cuda.get_device_name(0)}. Writing {path}")
    with open(path, "x") as f:   # "x" = refuse to overwrite an existing file
        for i, p in enumerate(prompts, 1):
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": p["prompt"]}]
            ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=False, **tmpl_kwargs)
            if not hasattr(ids, "shape"):      # newer transformers may return a dict
                ids = ids["input_ids"]
            ids = ids.to(model.device)
            t0 = time.time()
            with torch.no_grad():
                if a.thinking:
                    torch.manual_seed(i)   # fixed seed per question, so a rerun gives the same answers
                    out = model.generate(ids, max_new_tokens=a.max_new_tokens, do_sample=True,
                                         temperature=0.6, top_p=0.95, top_k=20)
                else:
                    out = model.generate(ids, max_new_tokens=a.max_new_tokens, do_sample=False)
            gen = out[0][ids.shape[1]:].tolist()
            extra = {}
            if a.thinking:
                # split at the last </think>: graded answer = text after it; reasoning kept separately
                cut = len(gen) - 1 - gen[::-1].index(think_end) if think_end in gen else None
                if cut is None:
                    reply = ""   # never finished thinking within the token limit -> no answer
                    extra = dict(thinking=tok.decode(gen, skip_special_tokens=True), thinking_finished=False,
                                 thinking_tokens=len(gen))
                else:
                    reply = tok.decode(gen[cut + 1:], skip_special_tokens=True).strip()
                    extra = dict(thinking=tok.decode(gen[:cut], skip_special_tokens=True), thinking_finished=True,
                                 thinking_tokens=cut)
                decoding = "sampled t=0.6 top_p=0.95 top_k=20 seed=question index"
            else:
                reply = tok.decode(gen, skip_special_tokens=True)
                decoding = "greedy"
            rec = dict(p, model=a.model, response=reply, seconds=round(time.time() - t0, 1),
                       new_tokens=len(gen), max_new_tokens=a.max_new_tokens,
                       decoding=decoding, time=datetime.datetime.now().isoformat(timespec="seconds"), **extra)
            f.write(json.dumps(rec) + "\n"); f.flush()
            note = "" if not a.thinking else (f", thinking {extra['thinking_tokens']}" + ("" if extra["thinking_finished"] else " (NOT FINISHED)"))
            print(f"[{i}/{len(prompts)}] {p['question_id']} done in {rec['seconds']}s, {rec['new_tokens']} tokens{note}", flush=True)
    print("Finished:", path)

if __name__ == "__main__":
    main()
