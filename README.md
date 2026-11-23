# gpt-researcher-webrouter

A [GPT Researcher](https://github.com/assafelovic/gpt-researcher) retriever plugin
for [WebRouter](https://github.com/Nimbleway/webrouter), an open-source library
that puts one search interface in front of many web search providers.

It works with no API key: with none set, searches go to the free keyless tiers
WebRouter supports, which are third-party services that receive your queries.
Every provider key you add (Tavily, Exa, Brave, Perplexity, Linkup and others)
gives WebRouter more providers to route to and fall back on, without changing
anything in GPT Researcher.

## Install

```bash
pip install gpt-researcher-webrouter
export RETRIEVER=webrouter
```

Install it in the same Python environment as GPT Researcher. It registers the
`webrouter` retriever under the `gpt_researcher.retrievers` entry point, so no
change to GPT Researcher is needed. Combine it with a built-in retriever, e.g.
`RETRIEVER=webrouter,arxiv`.

## Configuration

| Variable | Default | What it does |
| --- | --- | --- |
| `WEBROUTER_PROVIDER` | unset (`auto`) | Pin one provider, e.g. `tavily` or `exa`; a pinned provider has no fallback. Unset, WebRouter tries every provider it holds a key for, then the keyless ones, and falls back on an error or an empty result. |
| Provider keys | none | Read from the environment, e.g. `TAVILY_API_KEY`, `EXA_API_KEY`, `BRAVE_API_KEY`. WebRouter's [`.env.example`](https://github.com/Nimbleway/webrouter/blob/main/.env.example) lists every variable. |

## Behaviour

- Results are links with their title and a snippet (at most 500 characters),
  and GPT Researcher scrapes each page (`requires_scraping = True`).
- Domains in `query_domains` are passed to WebRouter as `include_domains`.
- Each search waits at most 30 seconds.
- On a failed search (no provider available, a timeout) it logs a warning and
  returns no results, so one failing retriever does not stop a research run.
  A misconfiguration, such as an unknown `WEBROUTER_PROVIDER`, is logged as an
  error.
- The package does not depend on `gpt-researcher`, so installing it never
  changes your GPT Researcher version; install it next to GPT Researcher 0.16.1
  or later.

Providers, their keys and the options each supports are listed in the
[WebRouter documentation](https://docs.webrouter.net/providers).

## Development

```bash
pip install -e ".[test]"
ruff check . && ruff format --check .
pytest
```

The tests replace WebRouter with a fake, so they run offline with no keys. With
`gpt-researcher` installed, one more test checks that GPT Researcher loads the
plugin by name.

## License

Apache 2.0
