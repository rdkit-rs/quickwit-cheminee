# Quickwit-Cheminee campaign status

The Ruby/importer campaign is **blocked on recovery of unpublished chemistry work**.
The local preparation branch is based on public PR3, not the unpublished DSL tip.
See the [decision log, contract audit and release checklist](docs/cheminee-campaign/README.md).
No new gem, Compose resource envelope, HA guarantee or performance result is claimed.

## Why this beats the pants off stinking old cheminee

That is the ambition; current evidence supports specific tradeoffs, not an overall
win. The recovered [controlled 100k study report](docs/cheminee-campaign/evidence/controlled-study-report.md)
compares the same immutable corpus, four CPUs, 14 GiB and three fresh ingestion
runs. These are historical PR3 observations, not measurements of new DSL or Ruby code.

| Measured case | Old Cheminee | Quickwit-Cheminee | Finding |
|---|---:|---:|---|
| Tuned ingestion, mean sampled peak process RSS | 2,986.0 MiB | 979.3 MiB, nested | Quickwit used about 67% less process RSS; not total machine memory |
| Tuned time until searchable | 308.46 s | 390.94 s matched-flat; 395.88 s nested | Old Cheminee loaded faster |
| Process-cold filtered graph query | 0.7780 s after merge | 11.8576 s nested | Old Cheminee was about 15.2 times faster |
| Repeated warm exact similarity | 0.9027 s after merge | 0.0099 s nested | Quickwit was faster for this identical cached request; not evidence for novel queries |

Old Cheminee also had lower cold exact-similarity latency after its inexpensive
supported merge: 1.1213 s versus 1.5563 s nested Quickwit. Payloads differ, OS page
cache was retained, and RSS omits much filesystem cache. See the report for ranges,
connection-overlap flags and scope. Original corpus/index bundles have not been
recovered in this session; the report was recovered from Library checkpoint v23.

Supplier-refresh correctness, Ruby wire behavior, low-memory coexistence with
Elasticsearch, HA/durability, stable generation-aware pagination and scale beyond
100k remain unproven. The existing chemistry routes offer bounded result sets,
not exhaustive cursor traversal. No arbitrary Elasticsearch/Searchkick compatibility
or correlated arrays-of-offers support is promised. Use separate offer documents
until correlation tests establish a stronger contract.

---

[![CI](https://github.com/quickwit-oss/quickwit/actions/workflows/ci.yml/badge.svg)](https://github.com/quickwit-oss/quickwit/actions?query=workflow%3ACI+branch%3Amain)
[![codecov](https://codecov.io/gh/quickwit-oss/quickwit/branch/main/graph/badge.svg?token=06SRGAV5SS)](https://codecov.io/gh/quickwit-oss/quickwit)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/quickwit-oss/quickwit/badge)](https://scorecard.dev/viewer/?uri=github.com/quickwit-oss/quickwit)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.0-4baaaa.svg)](CODE_OF_CONDUCT.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square)](LICENSE)
[![Twitter Follow](https://img.shields.io/twitter/follow/Quickwit_Inc?color=%231DA1F2&logo=Twitter&style=plastic)](https://twitter.com/Quickwit_Inc)
[![Discord](https://img.shields.io/discord/908281611840282624?logo=Discord&logoColor=%23FFFFFF&style=plastic)](https://discord.quickwit.io)
<br/>

<br/>
<br/>
<p align="center">
  <img src="docs/assets/images/logo_horizontal.svg#gh-light-mode-only" alt="Quickwit Cloud-Native Search Engine" height="40">
  <img src="docs/assets/images/quickwit-dark-theme-logo.png#gh-dark-mode-only" alt="Quickwit Cloud-Native Search Engine" height="40">
</p>

<h2 align="center">
Open-source search engine for observability (logs, traces, and soon metrics!).
</h2>

<h4 align="center">
  <a href="https://quickwit.io/docs/get-started/quickstart">Quickstart</a> |
  <a href="https://quickwit.io/docs/">Docs</a> |
  <a href="https://quickwit.io/tutorials">Tutorials</a> |
  <a href="https://discord.quickwit.io">Chat</a> |
  <a href="https://quickwit.io/docs/get-started/installation">Download</a>
</h4>
<br/>

<b>We just released Quickwit 0.8! Read the [blog post](https://quickwit.io/blog/quickwit-0.8) to learn about the latest powerful features!</b>

### **Quickwit is the fastest search engine on cloud storage. It's the perfect fit for observability use cases**

- [Log management](https://quickwit.io/docs/log-management/overview)
- [Distributed tracing](https://quickwit.io/docs/distributed-tracing/overview)
- Metrics support is on the roadmap

### 🚀 Quickstart

- [Search and analytics on Stack Overflow dataset](https://quickwit.io/docs/get-started/quickstart)
- [Trace analytics with Grafana](https://quickwit.io/docs/get-started/tutorials/trace-analytics-with-grafana)
- [Distributed tracing with Jaeger](https://quickwit.io/docs/get-started/tutorials/tutorial-jaeger)

<br/>

<video src="https://github.com/quickwit-oss/quickwit/assets/653704/020b94b9-deeb-4376-9a3a-b82e1168094c" controls="controls" style="max-width: 1200px;">
</video>

<br/>

# 💡 Features

- Full-text search and aggregation queries
- A subset of Elasticsearch-compatible APIs; client and operation compatibility require testing
- [Jaeger-native](https://quickwit.io/docs/distributed-tracing/plug-quickwit-to-jaeger)
- OTEL-native for [logs](https://quickwit.io/docs/log-management/overview) and [traces](https://quickwit.io/docs/distributed-tracing/overview)
- [Schemaless](https://quickwit.io/docs/guides/schemaless) or strict schema indexing
- Schemaless analytics
- Sub-second search on cloud storage (Amazon S3, Azure Blob Storage, Google Cloud Storage, …)
- Decoupled compute and storage, stateless indexers & searchers
- [Grafana data source](https://github.com/quickwit-oss/quickwit-datasource)
- Kubernetes ready - See our [helm-chart](https://quickwit.io/docs/deployment/kubernetes/helm)
- RESTful API

## Enterprise ready

- Multiple [data sources](https://quickwit.io/docs/ingest-data/) Kafka / Kinesis / Pulsar native
- Multi-tenancy: indexing with many indexes and partitioning
- Retention policies
- Delete tasks (for GDPR use cases)
- Distributed and highly available* engine that scales out in seconds (*HA indexing only with Kafka)

# 📑 Architecture overview

![Quickwit Distributed Tracing](./docs/assets/images/quickwit-overview-light.svg#gh-light-mode-only)![Quickwit Distributed Tracing](./docs/assets/images/quickwit-overview-dark.svg#gh-dark-mode-only)

- [Architecture overview]([https://quickwit.io/docs/distributed-tracing/overview](https://quickwit.io/docs/overview/architecture))
- [Log management](https://quickwit.io/docs/log-management/overview)
- [Distributed traces](https://quickwit.io/docs/distributed-tracing/overview)


# 📕 Documentation

- [Installation](https://quickwit.io/docs/get-started/installation)
- [Log management with Quickwit](https://quickwit.io/docs/log-management/overview)
- [Distributed Tracing with Quickwit](https://quickwit.io/docs/distributed-tracing/overview)
- [Ingest data](https://quickwit.io/docs/ingest-data/)
- [REST API](https://quickwit.io/docs/reference/rest-api)

# 📚 Resources

- [Blog posts](https://quickwit.io/blog/)
- [Youtube channel](https://www.youtube.com/@quickwit8103)
- [Discord](https://discord.quickwit.io)

# 🙋 FAQ

### How can I switch from Elasticsearch or OpenSearch to Quickwit?

Quickwit supports a large subset of Elasticsearch/OpenSearch API.

For instance, it has an ES-compatible ingest API to make it easier to migrate your log shippers (Vector, Fluent Bit, Syslog, ...) to Quickwit.

On the search side, the most popular Elasticsearch endpoints, query DSL, and even aggregations are supported.

The list of available endpoints and queries is available [here](https://quickwit.io/docs/reference/es_compatible_api), while the list of supported aggregations is available [here](https://quickwit.io/docs/reference/aggregation).

Let us know if part of the API you are using is missing!

If the client you are using is refusing to connect to Quickwit due to missing headers, you can use the `extra_headers` option in the [node configuration](https://quickwit.io/docs/configuration/node-config#rest-configuration) to impersonate any compatible version of Elasticsearch or OpenSearch.

### How is Quickwit different from traditional search engines like Elasticsearch or Solr?

The core difference and advantage of Quickwit is its architecture built from the ground to search on cloud storage. We optimized IO paths, revamped the index data structures and made search stateless and sub-second on cloud storage.

### How does Quickwit compare to Elastic in terms of cost?

We estimate that Quickwit can be up to 10x cheaper on average than Elastic. To understand how, check out our [blog post](https://quickwit.io/blog/commoncrawl/) about searching the web on AWS S3.

### What license does Quickwit use?

Quickwit is open-source under the Apache License, Version 2.0 - Apache-2.0.

### Is it possible to set up Quickwit for a High Availability (HA)?

HA is available for search, for indexing it's available only with a Kafka source.

# 🤝 Contribute and spread the word

We are always thrilled to receive contributions: code, documentation, issues, or feedback. Here's how you can help us build the future of log management:

- Start by checking out the [GitHub issues labeled "Good first issue"](https://github.com/quickwit-oss/quickwit/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22). These are a great place for newcomers to contribute.
- Read our [Contributor Covenant Code of Conduct](./CODE_OF_CONDUCT.md) to understand our community standards.
- [Create a fork of Quickwit](https://github.com/quickwit-oss/quickwit/fork) to have your own copy of the repository where you can make changes.
- To understand how to contribute, read our [contributing guide](./CONTRIBUTING.md).
- Set up your development environment following our [development setup guide](./CONTRIBUTING.md#development).
- Once you've made your changes and tested them, you can contribute by [submitting a pull request](./CONTRIBUTING.md#submitting-a-pr).

✨ After your contributions are accepted, don't forget to claim your swag by emailing us at hello@quickwit.io. Thank you for contributing!

# 💬 Join Our Community

We welcome everyone to our community! Whether you're contributing code or just saying hello, we'd love to hear from you. Here's how you can connect with us:

- Join the conversation on [Discord](https://discord.quickwit.io).
- Follow us on [Twitter](https://twitter.com/Quickwit_Inc).
- Check out our [website](https://quickwit.io/) and [blog](https://quickwit.io/blog) for the latest updates.
- Watch our [YouTube](https://www.youtube.com/channel/UCvZVuRm2FiDq1_ul0mY85wA) channel for video content.
