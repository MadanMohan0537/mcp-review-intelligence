# MCP Review Intelligence

A design brief for an MCP service that turns product reviews into traceable themes, sentiment summaries and comparison evidence.

**Status: concept stage.** This repository currently contains only this README. Review collection, sentiment analysis, MCP tools, storage and client integration have not been implemented.

## Intended value

Help an assistant answer questions such as “What problems recur in recent reviews?” with source-linked evidence rather than an unsupported opinion. A summary should retain review identifiers, source URLs, dates, sample size and representative excerpts.

## Proposed capabilities

| Capability | Intended output | Evidence requirement |
| --- | --- | --- |
| Collect reviews | Normalized review records | Source, capture date and stable identifier |
| Summarize sentiment | Distribution for a defined sample | Method, sample size and uncertainty |
| Identify themes | Recurring product issues and benefits | Traceable supporting reviews |
| Compare periods | Changes in observed themes | Comparable sources and date windows |
| Compare products | Side-by-side review findings | Disclosed differences in coverage |

These are design goals, not callable tools. A future tool contract should define pagination, filtering, structured errors and the distinction between a source rating and an inferred sentiment label.

## First implementation milestones

1. Support a permitted import format or one source adapter, with a documented review schema.
2. Deduplicate reviews and preserve provenance.
3. Establish a deterministic analysis baseline before adding optional model-assisted summaries.
4. Return exact evidence alongside every theme.
5. Expose validated MCP tools and test them with a real client.
6. Evaluate on labeled fixtures, including mixed sentiment, sarcasm, duplicate reviews and sparse data.

## Analysis boundaries

Reviews are a selected sample, not a census of customers. A high count of negative reviews does not establish population dissatisfaction or product causality. Do not invent quotes, infer a reviewer's personal traits, or hide differences in language, source or time coverage.

## Getting started

No package installation or server command is available yet. Publish startup and client configuration instructions only when the corresponding server and tests exist.

## Contributions and license

Start with the normalized schema, fixture dataset or analysis baseline. No license file is currently included; choose an explicit license before distributing implementation code or third-party review data.
