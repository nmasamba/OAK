# Cited answers over public technical manuals

We are a small internal engineering team. We keep a bounded collection of public
technical manuals and we want a tool that helps us find and cite the exact passage
that answers a question, and that drafts a short answer with those citations.
When the manuals do not support an answer, the tool must say so and point us at
manual review rather than guess.

Everyone who uses it is an internal engineer. One operator on the team runs it on
a single workstation. There are no external users and nobody outside the team is
affected by what it produces.

The tool only ever returns cited passages, drafts a cited answer, or abstains. It
recommends; it never acts on anything and every draft is reviewed by a person
before it is used anywhere. Nothing it does is hard to undo.

The manuals are public documents. No production data and no personal data is
involved, and none may be added later.

Answers must cite the right passage, must be accurate when they are supported by
the manuals, and must abstain when they are not. We would rather have a
well-calibrated refusal than a confident wrong answer.

It has to run locally on one machine with sixty-four bit x86 processors, thirty-two
gigabytes of memory and about one hundred gigabytes of storage, and it must keep
working with no network access after it is set up. We prefer open-source software
by default and either a locally hosted open model or no model at all; a plain
lexical search with cited passages and no generative model is an acceptable
baseline.

We do not yet know how many manuals we will index or how often they change, and
we have not decided which model licence and which measured hardware apply.
