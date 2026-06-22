# User Profiling — Implementation Status

> **User-facing docs:** settings and runtime behavior are documented in [`configuration_guide.md` → User profiling](configuration_guide.md#user-profiling).

Original design goal: split **user facts** (who they are) from **relationship disposition** (how the bot feels toward them), with passive ingest + async LLM distillation + prompt injection before replies.

**Current status (v1.5.x):** Phases **A–C shipped**. Phase **D–E** and optional Stage 6 modulations are **partial or pending**.

---

## Shipped (Phases A–C)

| Area | Implementation |
|------|----------------|
| Passive ingest | `lib/profile.py` `record_user_message`, counters, topics, buffer append |
| Disposition floats | `user_profiles` + `apply_disposition_delta` / `apply_outcome_delta` |
| Facts table | `profile_facts` with confidence, expiry support, keyword search |
| LLM distiller | `lib/profile_distill_llm.py`, `schedule/profile_distill.py` |
| Recall / inject | `recall_user_context()` → `[People context — internal]` in `lib/batching.py` |
| Reply modulation | `apply_profile_engagement()` scales organic reply chance |
| Settings UI | Memory tab profiling toggles; **Profiles** inspection tab |
| Slash | `/remember` (self), `/forget-me` |
| Imperfect recall | `profiling_imperfect_recall` setting |
| Light decay | `decay_dispositions()` after distill runs |
| Global profiles | One row per `(account, author_id)` — legacy per-guild rows merged at startup |

---

## Intentional divergences from original design

| Original design | Current code |
|-----------------|--------------|
| Per-guild profiles `(account, guild_id, author_id)` | **Global per user** per bot account (`GLOBAL_PROFILE_GUILD` in `lib/profile_store.py`) |
| `/remember @user` for other people | **Not implemented** — `/remember` only saves the caller's fact |
| Nightly consolidation cron | **Partial** — decay runs post-distill, no dedicated nightly job |

---

## Pending (Phase D — consolidation)

- [ ] Dedicated nightly/weekly consolidation job (beyond post-distill decay)
- [ ] Automatic duplicate-fact merge
- [ ] `profile_events` log pruning
- [ ] Scheduled `summary_l2` regeneration independent of distill
- [ ] Quiet outreach prioritizing absent high-familiarity users

---

## Pending (Phase E — polish)

- [ ] Group context line ("Also present: Alice (occasional), Bob (new)")
- [ ] Cross-channel recall ("you said in #dev yesterday") with privacy toggle
- [ ] `/remember @user` or per-user notes API

---

## Pending (Stage 6 — optional behavior modulation)

Designed as high-ROI extensions; not wired yet:

| System | Status |
|--------|--------|
| `gates.py` / reply chance | ✅ `apply_profile_engagement` |
| `engagement.py` per-user topics | ⚠️ Topics stored on profile; channel engagement unchanged |
| `reactions.py` warmth → emoji | ❌ |
| `style_hint.py` friend vs stranger | ❌ |
| `quiet_outreach.py` familiar absent users | ❌ |

---

## Module map

| Module | Role |
|--------|------|
| `lib/profile_store.py` | SQLite schema, buffers, facts, disposition |
| `lib/profile.py` | Ingest, recall, engagement modulation |
| `lib/profile_distill_llm.py` | Distiller prompt + JSON merge |
| `schedule/profile_distill.py` | Queue processor |
| `routes/profiles.py` | Profiles tab API |
| `handlers/slash_commands.py` | `/remember`, `/forget-me` |

---

## Related

- [`configuration_guide.md`](configuration_guide.md#user-profiling) — settings and behavior
- [`Roadmap.md`](Roadmap.md) — future work and done markers
- [`lib/memory.py`](lib/memory.py) — channel-centric recall (complementary, not replaced)
