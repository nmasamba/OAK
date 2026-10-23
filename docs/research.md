# Research at the point of design

OAK can look for newer open models and harnesses for one design case, only while its
candidates are not yet generated and each time you consent, and show what it finds as
alternative designs beside the curated ones. This page says what research is, what leaves your machine, what comes back, and what
it will not do. The decision record is
[ADR-0018](adr/architecture/0018-research-at-the-point-of-design.md).

## What it is, in plain words

When a case reaches `ready_for_candidates`, the case page asks "Look for newer options?"
and shows, word for word, what one research run would send and to whom. Nothing is sent
until you press **Run research**, and that needs the model-configuration token the API
prints at start, because research is the one step at that point that leaves the machine.
The default path is unchanged: generate without research and the case stays offline.

A run asks three public sources, anonymously, for open models and harnesses that fit the
confirmed intent, turns each answer into an untrusted component proposal, checks it with
deterministic gates, and records everything as a research snapshot beside the case. When
you then generate candidates, at most two **researched designs** join the four curated
ones, numbered from `candidate-05` and labelled like "Balanced, new". Each is shown with
its source, its date, the class of evidence behind every claim, and the plain reason it
cannot be selected in this release.

## What leaves the machine

| Sent | To | Never sent |
|---|---|---|
| Search terms drawn from closed vocabularies: for the Hub, the pipeline tags, the filters, the sort order and the inference-provider flag; for GitHub, the topics per harness kind, the archived flag and the freshness window | `huggingface.co` (model listings), `router.huggingface.co` (live routes and published prices), `api.github.com` (repository search, releases, tag commits) | The brief, the intent, your answers, your Hugging Face token, any name from your organisation; the capability keywords, the hardware class and the licence ids, which are applied on this machine only |

The plan is a read: `GET /v1/design-cases/{case_id}/research-plan` (or `oak research
--plan`) returns the hosts, the terms and their digest. A run must consent to exactly
those hosts and that digest; if the intent changed in between, the consent is refused
(`OAK-RESEARCH-CONSENT`) and nothing is sent. The requests are anonymous: no credential
goes to any of the three hosts, so the run shares the public rate limit of your address.

A run is bounded: at most thirty requests within sixty seconds, a size cap on every
answer, and a twenty-four-hour cache keyed by the terms digest. A redirect, an oversized
answer, a rate limit, an outage or an exhausted budget is a stable refusal
(`OAK-RESEARCH-REDIRECTED`, `-OVERSIZED`, `-RATE-LIMITED`, `-UNREACHABLE`, `-BUDGET`)
that is never retried and never cached; the operation records it and you may run again.

## What comes back

Every item found carries its source id, its tier, the date it was created or released,
and a list of claims. Each claim is labelled with one of seven **evidence classes**, and
that label is the only thing OAK asserts about it:

| Class | Shown as | Meaning |
|---|---|---|
| `served_by_live_route` | Live route | The router lists a live route for this model |
| `published_release` | Published release | A dated release exists, with a digest or a tag commit id |
| `published_by_source` | Published by source | The source's own listing says so (a price, a `gated` flag, a detected licence) |
| `measured_by_source` | Measured by source | The router publishes a probed figure, such as a throughput |
| `claimed_by_model_card` | Claimed by model card | The model's own card says so; its author controls it |
| `claimed_by_release_notes` | Claimed by release notes | The harness's notes say so; its author controls it |
| `unverified` | Unverified | Nothing backs it |

OAK quotes what each source claims and where. It never says a model is good, works well or
is the best, and a figure a source does not publish is `unknown` with that reason, never a
guessed number.

**Two tiers.** A model from one of the Hub namespaces the catalogue lists as trusted, or a
harness on the owner-reviewed list in `catalogue/research/harness-repositories.yaml`,
passes the tier gate on its own. Anything else is **unvetted**: it needs your review, a
recorded decision with a rationale (`oak research review <item> --accept|--reject
--rationale-file <file>`), before it can enter a design. The harness list ships as a draft
until the owner records a review of it, and the file says so.

**The gates** (`community-research-gates-1.0.0`) refuse an item whose licence is not on the
allowlist (`Apache-2.0`, `MIT`, `BSD-3-Clause`), that is gated, archived or disabled, that
is undated or older than the freshness window, that is dated in the future, that names
nothing the capability map asks for, or whose text fails the allowlist normalisation.
Every string is normalised by allowlist: NFKC, no control or format character, an ASCII
identifier shape, bounded lengths and no forbidden word; an item that fails is listed by
digest only, with its reason. A harness is paired with a model only when its release notes
name the model's family as a whole token, and the pairing shows the class of every claim
it rests on.

## What a researched design is, and is not

- It keeps its pattern's variant and label plus the one closed suffix: "Balanced, new".
  Its label is never built from a model or repository name.
- It is listed `infeasible` with every reason: its licence review is pending, and the
  resources, deployment modes and figures its sources do not publish are unknown.
- Under the compare-only rule (`community-compare-only-1.0.0`) a researched design whose
  only failures are pending reviews or unpublished values joins the frontier comparison,
  with its estimates where they exist, but `select` refuses it (`OAK-SELECT-INFEASIBLE`).
  Making a reviewed researched design selectable is planned work, not part of this release.
- It is never the baseline. Only the curated `simpler_baseline` candidate is.
- Nothing installs it. The runner, the bundle and the architecture document only ever
  describe the selected, curated design.

## Where it shows

- **The case page**: the Research moment, the consent card, the run watched in place, the
  results as chips (found, passed, needing your review), each item with its claims and
  evidence words, and the review form for an unvetted item.
- **Designs**: the **New** chip, the "…, new" label, the evidence chips, the Source and
  Release date columns, an unknown estimate's own reason, and why the design cannot be
  selected.
- **The report**: appendix G, "What research found, and what each source claims", present
  only when the case holds a research snapshot; slide 2 names the run and both rule sets;
  appendix E lists the researched evidence by its untrusted source type; appendix F binds
  the snapshot, every researched manifest and every review by digest. Quoted claims live in
  appendix G only; a main slide names a researched design by its id, label, evidence word,
  date, licence id and digest, and nothing an author wrote.
- **The downloads sheet**: the research snapshot, checked by digest like every other file.
- **The CLI and REST**: `oak research --plan`, `oak research --consent <digest>`,
  `oak research review`; `GET …/research-plan`, `POST …:research` (`202`, an operation),
  `POST …:review-research-item`. All work locally and with `--server`, passing the token
  as `oak report --narrative` does. MCP has no research tools.

## The fixture source

Set `OAK_RESEARCH_FIXTURES=<directory>` for the API and the worker (or for a local CLI run)
and every research request is answered from recorded JSON in that directory instead of
contacting any host; set on the worker alone, every run is refused with
`OAK-RESEARCH-CONSENT`, because the API's plan would still name the live hosts. It exists for the test
suites and the throwaway Compose stack; a snapshot it produces says `source_mode: fixture`,
lists no host, and every figure from it reads "synthetic estimate" in a report. The
variable is safety-relevant and documented in [configuration.md](configuration.md). The
recorded answers under `tests/fixtures/research/` are synthetic: "Fixturelm" is not a real
model and `fixture-forge/fixturelm-serve` is not a real repository.

## What research does not do

- It does not check a claim. A licence from a model card is the card's claim; a throughput
  from the router is the router's figure. The evidence word says which
  ([`RR-049`](security/residual-risk.md)).
- It does not identify what would run. A researched component's identity is the commit id
  or tag the source lists, not a digest of its weights or binaries
  ([`RR-053`](security/residual-risk.md)).
- It does not vouch for an unvetted harness. Your recorded review admits it to comparison;
  the review is your judgement ([`RR-051`](security/residual-risk.md)).
- It does not hide what it sends. The terms reveal the shape of what you are designing to
  the three hosts, and the consent card shows exactly that ([`RR-048`](security/residual-risk.md)).
- It does not guarantee an answer. The budget is anonymous and shared with everyone behind
  your address, so a busy address may be rate-limited; a cached result inside its
  twenty-four-hour window may be a day old, and its `checked_at` says so
  ([`RR-050`](security/residual-risk.md)).
- It does not select, approve or install anything ([`RR-052`](security/residual-risk.md)).

See also [interfaces.md](interfaces.md) for the routes and commands,
[security/threat-coverage.md](security/threat-coverage.md) for the tests behind each
claim, and the user manual's section on looking for newer options.
