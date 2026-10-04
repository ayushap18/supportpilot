# What the baseline misses

The reports compare deterministic fixture implementations on synthetic RelayDesk cases. They do not measure a live LLM.

Three representative baseline failures from the frozen held-out run:

1. **`held-05`, revoked account:** the baseline escalates because it cannot verify account state. The tool workflow reads the authorized synthetic account and cites the account policy and lookup result.
2. **`held-06`, account-specific rate allowance:** the baseline cannot verify which plan applies. The workflow looks up the starter plan and supplies the recorded 60-request allowance alongside backoff guidance.
3. **`held-07`, active service incident:** the baseline escalates without confirming the incident or the expected incident-response guidance. The workflow checks synthetic service health and incident records, escalates to incident response, and avoids inventing a recovery time.

Reference-document retrieval is incomplete: the development run retrieves every required reference in 26/30 cases and the held-out run in 18/20 distinct cases. Correct route selection does not mean every reference was retrieved or every claim was semantically validated. The reports preserve those separate measures.

The full workflow matches the expected fixture outcomes in the reported runs. That result should be read alongside the limitations: deterministic routing, synthetic examples, substring fact checks, untested live credentials, and pending human citation review. A live model can fail differently, especially on ambiguous tickets or injected text.

Held-out outputs have now been inspected. Keep this set for regression checks and create a new held-out set if its failures later inform prompt or retrieval changes.
