# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: S101
# ruff: noqa: D103
# ruff: noqa: E501
# ruff: noqa: PLC2401, N802

import io

from feed_release.handler import parse_atom_feed


def test_feedが0件():
    # prepare
    owner = "owner"
    repo = "repo"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/astral-sh/ruff/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/astral-sh/ruff/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
</feed>
"""
    res = io.BytesIO(xml.encode("utf-8"))

    # exec
    act = parse_atom_feed(res)  # ty:ignore[invalid-argument-type]

    # verify
    assert act is None


def test_feedが1件():
    # prepare
    owner = "owner"
    repo = "repo"
    release_id = "tag:github.com,2009:Repository/123456789/0.1.0"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/astral-sh/ruff/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/astral-sh/ruff/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
  <entry>
    <id>{release_id}</id>
    <updated>2025-12-19T04:37:41+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/astral-sh/ruff/releases/tag/0.14.10"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
</feed>
"""
    res = io.BytesIO(xml.encode("utf-8"))

    # exec
    act = parse_atom_feed(res)  # ty:ignore[invalid-argument-type]

    # verify
    assert release_id == act


def test_feedが2件():
    # prepare
    owner = "owner"
    repo = "repo"
    release_id = "tag:github.com,2009:Repository/123456789/0.1.0"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/astral-sh/ruff/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/astral-sh/ruff/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
   <entry>
    <id>{release_id}</id>
    <updated>2025-12-19T04:37:41+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/astral-sh/ruff/releases/tag/0.14.10"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
 <entry>
    <id>dummy-id</id>
    <updated>2025-12-19T04:37:41+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/astral-sh/ruff/releases/tag/0.14.10"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
</feed>
"""
    res = io.BytesIO(xml.encode("utf-8"))

    # exec
    act = parse_atom_feed(res)  # ty:ignore[invalid-argument-type]

    # verify
    assert release_id == act
