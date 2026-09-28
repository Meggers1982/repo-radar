# Learned adjustments

Auto-applied by `scripts/learn-from-feedback.mjs`, run monthly. Deterministic pattern mining over Saved/Dismissed on the dashboard -- no LLM, no judgment calls beyond the thresholds in the script. Review `config/lanes.json` diffs same as any other commit; anything here can be hand-reverted.

## 2026-09-28

**Applied:**

- **owner denylist:** `ekkolearnai` (2 dismissals, 0 saves)
- **lane 2 topic:** `cursor` added (6 saved repos, led under lane 2)

**Suggested, review and fold in by hand:**

- **lane 1 topic (suggested, not applied):** `ai` -- 14 saved repos led under lane 1, but topic:ai matches 182,747 repos on GitHub, too broad to trust as a lane signal without a human call
- **lane 2 topic (suggested, not applied):** `agent-skills` -- 11 saved repos led under lane 2, but topic:agent-skills matches 26,825 repos on GitHub, too broad to trust as a lane signal without a human call
- **lane 2 topic (suggested, not applied):** `claude` -- 11 saved repos led under lane 2, but topic:claude matches 53,875 repos on GitHub, too broad to trust as a lane signal without a human call
- **lane 1 topic (suggested, not applied):** `anthropic` -- 8 saved repos led under lane 1, but topic:anthropic matches 24,627 repos on GitHub, too broad to trust as a lane signal without a human call
- **lane 1 topic (suggested, not applied):** `codex` -- 6 saved repos led under lane 1, but topic:codex matches 34,715 repos on GitHub, too broad to trust as a lane signal without a human call
- **exclude phrase (suggested, not applied):** `workspace` (6 dismissed repos across 5 owners, 0 saved: EKKOLearnAI/hermes-studio, EKKOLearnAI/ekko-studio, siyuan-note/siyuan, …)
- **exclude phrase (suggested, not applied):** `local-first` (4 dismissed repos across 3 owners, 0 saved: EKKOLearnAI/hermes-studio, EKKOLearnAI/ekko-studio, KunAgent/Kun, …)
- **exclude phrase (suggested, not applied):** `chat` (4 dismissed repos across 3 owners, 0 saved: EKKOLearnAI/hermes-studio, EKKOLearnAI/ekko-studio, Osmantic/ODS, …)

_46 saved, 56 dismissed in repo_state at run time._

