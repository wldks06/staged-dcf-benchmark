"""Check, without a GPU, that vLLM 0.10.1 + transformers 5 (the V100 environment) handles each V100 model after
run_model.apply_compat_patches(): the tokenizer goes through vLLM's own wrapper, a chat prompt round-trips,
and the model config vLLM reads keeps the RoPE settings of config.json (transformers 5 moved rope_theta /
rope_scaling into rope_parameters; if vLLM 0.10.1 then fell back to a default base, the model would run with
the wrong positions and produce degraded answers without any error).

    python compat_check.py qwen25-7b fin-r1 dianjin-7b llama31-8b fino1-8b qwen3-8b fin-o1-8b
    (exit code 1 if anything fails; slurm/compat_check.sbatch)
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_model import MODELS, apply_compat_patches  # noqa: E402

print("patches:", apply_compat_patches())
import transformers, vllm  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402
from vllm.transformers_utils.tokenizer import get_tokenizer  # noqa: E402
from vllm.engine.arg_utils import EngineArgs  # noqa: E402
print("vllm", vllm.__version__, "| transformers", transformers.__version__, flush=True)

bad = 0
for preset in sys.argv[1:]:
    hf_id = MODELS[preset][0]
    print(f"\n== {preset} ({hf_id})", flush=True)
    try:
        tok = get_tokenizer(hf_id)                      # vLLM's wrapper: this is what crashed in job 12259427
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "What is 2+2? End with FINAL ANSWER: 4"}]
        text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        ids = tok(text, add_special_tokens=False)["input_ids"]
        back = tok.decode(ids)
        print(f"  tokenizer {type(tok).__name__}: {len(ids)} ids, round trip {'ok' if back == text else 'DIFFERS'}, "
              f"specials {len(tok.all_special_tokens_extended)}, eos {tok.eos_token!r}")
        raw = json.load(open(hf_hub_download(hf_id, "config.json")))
        mc = EngineArgs(model=hf_id, dtype="float16", max_model_len=32768).create_model_config()   # vLLM's own path
        cfg = mc.hf_config
        want_theta = raw.get("rope_theta") or (raw.get("rope_parameters") or {}).get("rope_theta")
        want_scal = raw.get("rope_scaling")
        default = 10000 if "Llama" in type(cfg).__name__ else 1000000      # vLLM 0.10.1 model-code fallbacks
        got_theta, got_scal = getattr(cfg, "rope_theta", default), getattr(cfg, "rope_scaling", None)
        ok_theta = want_theta is None or (got_theta is not None and float(got_theta) == float(want_theta))
        strip = lambda d: {k: v for k, v in (d or {}).items() if k != "rope_theta"} or None
        ok_scal = strip(got_scal) == strip(want_scal)
        print(f"  config {type(cfg).__name__}: rope_theta config.json={want_theta} vLLM sees={got_theta} [{'ok' if ok_theta else 'MISMATCH'}]; "
              f"rope_scaling config.json={want_scal} vLLM sees={got_scal} [{'ok' if ok_scal else 'MISMATCH'}]; "
              f"max_position_embeddings {getattr(cfg, 'max_position_embeddings', None)}, vLLM max_model_len {mc.max_model_len}")
        bad += (back != text) + (not ok_theta) + (not ok_scal)
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"  FAILED: {type(e).__name__}: {e}")
print("\nRESULT:", "ALL OK" if not bad else f"{bad} problem(s)")
sys.exit(1 if bad else 0)
