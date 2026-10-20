# Shortcuts for the steps in docs/REPRODUCE.md. Everything here runs on a laptop without a GPU.
# Outputs go to $(OUT) (default /tmp/staged-dcf), never into results/, so the published files stay untouched.

PY  ?= python3
OUT ?= /tmp/staged-dcf
Q   := data/questions

.PHONY: help tables table1 regrade audit questions engine-test misses all

help:
	@echo "make tables       rebuild the paper tables and the summary from results/graded and compare them with results/"
	@echo "make table1       print Table I (questions by valuation set and tier)"
	@echo "make regrade      regrade every answer in results/answers, rebuild the tables, compare both with the published files"
	@echo "make audit        audit the answer keys of the three question sets (checks A to E)"
	@echo "make questions    rebuild the 2019/2022 and held-out question sets and compare them with data/questions"
	@echo "make misses       list the incorrect final answers of the pilot run of Qwen3-32B"
	@echo "make engine-test  install the engine (dcfbench) in a virtual environment and run its tests"
	@echo "make all          everything above"
	@echo "Outputs go to $(OUT)."

tables:
	cd pipeline && $(PY) analyze_paper.py --graded ../results/graded --out $(OUT)/paper_tables
	@for f in results/paper_tables/*; do cmp -s $$f $(OUT)/paper_tables/$$(basename $$f) && echo "identical  $$(basename $$f)" || echo "DIFFERENT  $$(basename $$f)"; done
	cd pipeline && $(PY) -B summarize.py --graded ../results/graded --out $(OUT)/summary > /dev/null
	@for f in results/summary/*; do cmp -s $$f $(OUT)/summary/$$(basename $$f) && echo "identical  summary/$$(basename $$f)" || echo "DIFFERENT  summary/$$(basename $$f)"; done

table1:
	$(PY) pipeline/count_questions.py

regrade:
	rm -rf $(OUT)/graded && mkdir -p $(OUT)/graded
	cd pipeline && $(PY) -B grade.py --qa ../$(Q)/QA_set_v2.json --self-test
	@cd pipeline && for f in ../results/answers/*/answers_*.jsonl.gz; do \
	  m=$$(basename $$(dirname $$f)); mkdir -p $(OUT)/graded/$$m; \
	  case $$f in *_ver03_newco_*) qa=../$(Q)/QA_set_ver03_newco.json;; *_ver03_*) qa=../$(Q)/QA_set_ver03.json;; *) qa=../$(Q)/QA_set_v2.json;; esac; \
	  for mode in qa plan; do $(PY) -B grade.py --qa $$qa --tolerance $$mode --out $(OUT)/graded/$$m --answers $$f > /dev/null; done; \
	  $(PY) -B grade.py --qa $$qa --tolerance plan --include-thinking --out $(OUT)/graded/$$m --answers $$f > /dev/null; \
	done
	@n=0; d=0; for g in $(OUT)/graded/*/*; do n=$$((n+1)); cmp -s $$g results/graded/$${g#$(OUT)/graded/} || { d=$$((d+1)); echo "DIFFERENT $${g#$(OUT)/graded/}"; }; done; \
	  echo "regraded $$n files, $$d differ from results/graded"
	cd pipeline && $(PY) analyze_paper.py --graded $(OUT)/graded --out $(OUT)/paper_tables_regraded
	@for f in results/paper_tables/*; do cmp -s $$f $(OUT)/paper_tables_regraded/$$(basename $$f) && echo "identical  $$(basename $$f)" || echo "DIFFERENT  $$(basename $$f)"; done

audit:
	@cd pipeline && for s in QA_set_v2 QA_set_ver03 QA_set_ver03_newco; do \
	  $(PY) audit_questions.py --qa ../$(Q)/$$s.json --out $(OUT)/audit > /dev/null; \
	  for c in A_answer_keys B_reproducible_from_prompt D_rubric_consistency E_case_flags; do \
	    cmp -s $(OUT)/audit/$${s}_$$c.csv ../results/audit/$${s}_$$c.csv && echo "identical  $${s}_$$c" || echo "DIFFERENT  $${s}_$$c"; done; \
	  echo "           $${s}_C_raw_filings: market-value rows need the Yahoo price files, which are not redistributed"; \
	done

questions:
	mkdir -p $(OUT)/questions
	cd pipeline && $(PY) build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../$(Q)/QA_set_v2.json \
	  --dates 2019-12-31,2022-12-31 --out $(OUT)/questions/QA_set_ver03.json > /dev/null
	cd pipeline && $(PY) build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../$(Q)/QA_set_v2.json \
	  --dates 2025-12-31 --new-companies --out $(OUT)/questions/QA_set_ver03_newco.json > /dev/null
	@$(PY) -c "import json; \
	[print(n, 'questions, rubric and cases identical' if all(json.load(open('$(Q)/'+n+'.json'))[k] == json.load(open('$(OUT)/questions/'+n+'.json'))[k] for k in ('questions', 'rubric', 'cases_used')) else 'DIFFERENT') for n in ('QA_set_ver03', 'QA_set_ver03_newco')]"

misses:
	cd pipeline && $(PY) list_misses.py --graded ../results/graded/pilot --answers ../results/answers/pilot \
	  --config Qwen3-32B_think --mode qa --out $(OUT)/pilot_qwen3-32b_misses.csv
	@cmp -s $(OUT)/pilot_qwen3-32b_misses.csv results/error_analysis/pilot_qwen3-32b_misses.csv && echo "identical  pilot_qwen3-32b_misses.csv"

engine-test:
	$(PY) -m venv $(OUT)/venv
	$(OUT)/venv/bin/python -m pip install -q -e "engine[dev]"
	cd engine && DCFBENCH_ROOT=$(CURDIR)/engine $(OUT)/venv/bin/python -m pytest -q -p no:cacheprovider

all: table1 tables questions audit misses regrade engine-test
