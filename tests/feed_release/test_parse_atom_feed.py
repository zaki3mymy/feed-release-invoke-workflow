# ruff: noqa: D100
# ruff: noqa: ANN201
# ruff: noqa: S101
# ruff: noqa: D103
# ruff: noqa: E501
# ruff: noqa: PLC2401, N802

import io
from datetime import datetime, timedelta, timezone

from feed_release.handler import parse_atom_feed


def test_feedが0件():
    # prepare
    owner = "owner"
    repo = "repo"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
</feed>
"""

    # exec
    act = parse_atom_feed(xml)

    # verify
    assert act is None


def test_feedが1件():
    # prepare
    owner = "owner"
    repo = "repo"
    release_id = "tag:github.com,2009:Repository/123456789/0.1.0"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
  <entry>
    <id>{release_id}</id>
    <updated>2026-01-01T12:34:56+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/0.1.0"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
</feed>
"""

    # exec
    act = parse_atom_feed(xml)  # ty:ignore[invalid-argument-type]

    # verify
    assert act is not None
    assert release_id == act.id
    exp_dt = datetime(2026, 1, 1, 12, 34, 56, tzinfo=timezone(timedelta(hours=9)))
    assert exp_dt == act.updated


def test_feedが2件():
    # prepare
    owner = "owner"
    repo = "repo"
    release_id = "tag:github.com,2009:Repository/123456789/0.1.0"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xml:lang="en-US">
  <id>tag:github.com,2008:https://github.com/owner/repo/releases</id>
  <link type="text/html" rel="alternate" href="https://github.com/owner/repo/releases"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/{owner}/{repo}/releases.atom"/>
  <title>Release notes from {repo}</title>
  <updated>2025-12-19T04:08:17+09:00</updated>
   <entry>
    <id>{release_id}</id>
    <updated>2026-01-01T12:34:56+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/0.1.0"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
 <entry>
    <id>dummy-id</id>
    <updated>2026-01-01T12:34:56+09:00</updated>
    <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/0.1.0"/>
    <title>0.1.0</title>
    <content type="html">&lt;h2&gt;Release Notes&lt;/h2&gt;</content>
    <author>
      <name>github-actions[bot]</name>
    </author>
  </entry>
</feed>
"""

    # exec
    act = parse_atom_feed(xml)  # ty:ignore[invalid-argument-type]

    # verify
    assert act is not None
    assert release_id == act.id
    exp_dt = datetime(2026, 1, 1, 12, 34, 56, tzinfo=timezone(timedelta(hours=9)))
    assert exp_dt == act.updated
