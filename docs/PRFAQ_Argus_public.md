# PRFAQ: Argus — AI-Assisted Exception Analysis for Engineering Teams

---

## Press Release

**FOR IMMEDIATE RELEASE**

### Engineering Teams Ship Faster and Sleep Better as Argus Catches Escaped Defects Before They Reach Production

*AI-powered exception analyst correlates observability data with application code to deliver actionable fix recommendations — directly from the CD pipeline*

Today the team behind Argus announced the general availability of Argus, an open source AI-assisted exception analysis tool that helps software engineering teams identify, triage, and fix escaped defects before they impact customers. Built initially to address the scale challenges of a high-volume transaction platform, Argus has been released as an open source project so any engineering team can benefit.

Argus integrates with existing observability stacks — including Sumo Logic, Grafana Loki, Tempo, and Prometheus — to pull exception data from staging and QA environments, correlate it with application code and static analysis signals from SonarQube, and produce structured fix recommendations as draft pull requests. Engineers no longer need to manually pivot between log dashboards, code repositories, and static analysis tools to understand what broke and why.

"We were catching real bugs in staging that would have reached production and affected customers," said the SRE lead who built Argus. "The tool paid for itself in the first week. Now we're open-sourcing it so other teams don't have to solve this problem from scratch."

Argus runs locally or as a CD pipeline stage. It is model-agnostic — teams can use Anthropic Claude, OpenAI GPT-4o, Google Gemini, or locally-hosted models via Ollama. A built-in eval framework tracks recommendation quality over time using a five-point scoring rubric grounded in real pull request outcomes, giving teams objective data on whether AI-assisted analysis is improving.

Argus is available today at github.com/gotoplanb/argus under the MIT license.

---

## Frequently Asked Questions

### User FAQs

---

**Q: What problem does Argus solve?**

A: Engineering teams operating at scale spend significant time manually triaging exceptions in staging and QA environments before releases. The process typically requires an engineer to query an observability platform, download log data, cross-reference it with the application codebase, check static analysis results, form a hypothesis, and write a fix — often across four or five different tools with no automation connecting them. At high transaction volumes, staging environments generate hundreds of exceptions per deployment cycle, many of which are noise from background jobs and cache loaders. Without automated triage, escaped defects slip through to production or engineers waste time chasing false positives.

Argus automates the correlation step. It pulls exception data from your observability stack, loads the relevant application code, incorporates SonarQube signals, and produces a structured analysis with root cause hypothesis, severity estimate, noise classification, and a specific fix recommendation. The output is a draft pull request — not a report that requires further interpretation.

---

**Q: How does Argus fit into an existing observability stack? Does it replace anything?**

A: Argus complements existing tools — it does not replace them. It sits above your observability platform as an analysis layer. Argus queries either an existing platform like Sumo Logic directly via its search job API, or Watchtower (a companion open source LGTM stack built on Grafana Alloy, Loki, Tempo, and Prometheus) for teams who want a local-first workflow.

For teams already using Sumo Logic, Datadog, or similar platforms, Argus adds AI-assisted triage on top of what you already have. Nothing needs to change in how you instrument your applications.

---

**Q: What observability platforms does Argus support?**

A: Currently Sumo Logic (via the search job API) and any Grafana LGTM-compatible stack (Loki for logs, Tempo for traces, Prometheus for metrics) via standard HTTP endpoints. SonarQube is supported as an additional signal source for static analysis context. Support for additional backends is straightforward to add via the data source plugin interface in `sources/`.

---

**Q: Which AI models does Argus support?**

A: Argus is model-agnostic. It uses Simon Willison's `llm` Python library as an abstraction layer, which means any model supported by `llm` works out of the box. This includes Anthropic Claude (default: claude-sonnet-4-6), OpenAI GPT-4o, Google Gemini, and locally-hosted models via Ollama. Teams switch models by changing a single environment variable (`ARGUS_MODEL`) and installing the appropriate `llm` plugin. No code changes required.

This design decision was deliberate: model capabilities and pricing change rapidly, and we did not want to hard-code a dependency on any single provider.

---

**Q: How does Argus know which exceptions are signal versus noise?**

A: Staging environments generate a disproportionate number of exceptions relative to production because background jobs — cache loaders, reservation updaters, and similar async processes — run continuously and often fail against incomplete test data or misconfigured endpoints. These failures rarely represent actionable application defects.

Argus's analysis prompt explicitly instructs the model to classify each exception as likely signal or likely noise, with noise defined as exceptions originating from background jobs or infrastructure-level processes rather than application request paths. This classification is included in every finding so engineers can quickly filter to the exceptions that matter.

---

**Q: How do we know if Argus recommendations are actually good?**

A: Argus includes a built-in eval framework. After a draft PR is reviewed by a code owner, engineers record the outcome using `argus score`. The scoring rubric is:

| Score | Meaning |
|-------|---------|
| 5 | PR accepted as-is |
| 4 | Right solution, minor placement adjustment, used without meaningful changes |
| 3 | Right solution, wrong abstraction or location, required rework but core idea was used |
| 2 | Wrong solution, distracted the team, some time lost |
| 1 | Completely wrong, significant engineering time wasted |

Code owner comments on the draft PR are captured and auto-classified for sentiment. Over time, the eval data reveals which exception types Argus handles well, which models perform better for your codebase, and whether prompt or tooling changes are improving recommendation quality. This is the same eval-driven iteration loop used by AI model providers themselves, applied to a production engineering workflow.

---

**Q: Can Argus run in a CD pipeline instead of manually?**

A: Yes — this is the intended end state. Argus is designed from the start to support both interactive local use and non-interactive pipeline execution. Every CLI command accepts all parameters as arguments (not just interactively) and returns meaningful exit codes: 0 for success, 1 for analysis errors, 2 for connectivity failures. A pipeline stage that runs `argus run --source watchtower --environment staging --time-range 1h` after a QA suite completes is a straightforward addition to any CD configuration.

The local interactive workflow is the starting point because it lets engineers validate recommendation quality and build the eval dataset before automating. Once your eval scores are consistently in the 3–5 range, pipeline integration is low-risk.

---

**Q: How is run data stored and managed?**

A: Argus uses a two-tier storage model. Raw log data (exception CSVs, finding markdown files) lives on disk under a `runs/` directory organized by run ID — this keeps the database lean and avoids trying to store large log payloads in SQLite. Metadata — run parameters, finding summaries, eval scores, model used — lives in a local SQLite database at `~/.argus/argus.db`.

This design means the tool works entirely locally with no external database dependency, and run data can be inspected with any standard file or SQLite tool.

---

**Q: Is Argus safe to run against production data?**

A: Argus is a read-only tool with respect to your observability infrastructure. It pulls data via standard query APIs and does not write back to Sumo Logic, Loki, or any other data source. Exception data is written to your local disk only. That said, exception logs often contain sensitive customer or transaction data, and teams should apply appropriate data handling policies before enabling Argus against production environments. The current recommended use case is staging and QA, where realistic traffic patterns exist but PII handling requirements are typically less restrictive.

---

### Adopter FAQs

---

**Q: Why build this instead of buying a commercial solution?**

A: Commercial APM and exception tracking tools (Sentry, Datadog Error Tracking, etc.) are excellent at aggregating and surfacing exceptions. None of them produce code-level fix recommendations correlated with your specific codebase, your static analysis results, and your accumulated institutional knowledge about past exceptions. The AI analysis layer is the differentiator, and it requires tight integration with the code repository and lessons learned over time — something a generic SaaS product cannot provide out of the box.

Building Argus also gave us full control over the eval framework, which is how we measure whether AI-assisted development tooling is actually improving engineering outcomes rather than just generating activity.

---

**Q: What is the engineering investment to adopt Argus?**

A: For local use by an individual SRE or engineering lead, setup is under an hour: install the Python package, configure `.env` with observability credentials, install an `llm` provider plugin, and run `argus status` to verify connectivity. No infrastructure changes required.

For team-wide adoption with CD pipeline integration, the additional investment is instrumenting your QA environment to dual-write OTLP telemetry to a Watchtower instance (a companion open source project), which typically takes a day or two. Pipeline integration is then a matter of adding a post-QA stage to your existing CD configuration.

---

**Q: How does Argus relate to Watchtower?**

A: Watchtower is a companion open source project that provides local and cloud-deployable observability infrastructure built on the Grafana LGTM stack (Loki, Grafana, Tempo, Mimir) with Grafana Alloy for telemetry ingestion. Watchtower can dual-write to existing backends like Sumo Logic, making it additive rather than disruptive to current tooling.

Argus can query Watchtower as a data source, which provides two advantages over querying a production platform directly: Watchtower holds correlated traces, logs, and metrics in a single stack queryable via standard APIs, and it supports local synthetic data generation for testing Argus itself without requiring real exception data. The two projects are complementary — Watchtower is the data platform, Argus is the AI analyst that sits on top of it.

---

**Q: Why does this repo live on a personal GitHub account rather than an organization?**

A: For many teams adopting open source tooling at an early stage, moving projects under a company GitHub organization introduces governance overhead — open source review processes, security audit obligations, IP assignment policies, legal review of licensing — that is not warranted until the project has proven its value. A personal GitHub account is the pragmatic starting point: the code is publicly available, MIT licensed, and fully functional. Migration to an organization is straightforward when and if circumstances make it worthwhile.

---

**Q: Why is this open source?**

A: Engineering tooling for exception analysis and observability pipeline integration is not a business differentiator for the teams that build and use it. The competitive advantage of any product company lies in what they build for their customers, not in the internal tools their engineers use to maintain reliability. Those tools are a means to an end, not a moat.

Open sourcing Argus serves adopters in three concrete ways. First, it accelerates iteration — external contributors encounter use cases and edge cases no single team would encounter internally, and good ideas from other engineering teams make the tool better for everyone. Second, it reduces maintenance burden over time as the community shares in the work of keeping dependencies current and adding integrations. Third, it is good for engineering culture — teams that open source useful tooling attract engineers who want to work on well-crafted infrastructure.

There is no scenario in which a team would benefit from keeping tooling like this proprietary. Open source is the straightforward choice.

---

**Q: What are the known limitations?**

A: Three limitations are worth understanding before adopting Argus.

First, **recommendation quality is not uniform**. Argus performs well on common exception patterns where the root cause is localized to a single file or method. It performs less well on distributed systems failures involving multiple services, race conditions, or infrastructure-level issues. The eval framework exists specifically to make this visible rather than hidden.

Second, **engineer trust calibration takes time**. Teams adopting AI-assisted analysis need to develop intuition for when to trust recommendations and when to dig deeper. The first few weeks of use typically involve more manual verification than steady state. This is a feature of the workflow, not a bug — the eval scoring process accelerates trust calibration by making recommendation quality explicit.

Third, **exception data may contain sensitive information**. Teams should review their data handling policies before enabling Argus against environments that process customer PII or payment data. Staging is the recommended starting point.

---

**Q: What does success look like?**

A: Three measurable outcomes indicate Argus is working well for a team:

1. Average eval score of 3.5 or higher across all scored findings, indicating recommendations are consistently directionally correct even when not accepted verbatim.
2. Argus running as an automated stage in at least one CD pipeline, with a documented reduction in escaped defects reaching production from that pipeline.
3. Engineers spending less time manually triaging staging exceptions and more time acting on clear, prioritized recommendations.
