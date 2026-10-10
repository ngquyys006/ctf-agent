"""Memory tests: the four memory modules, the Markdown format, and the
SQLite catalog that must stay in step with the files.

Covers search/read, Knowledge creation and update, Experience storage,
duplicate handling, and the rebuild of the catalog from Markdown
(spec sections 8, 9, 14-17, 38-40).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
import unittest

import config
from memory import save_experience, save_knowledge, search, update_knowledge
from tests import _util

_STATE = {}


def setUpModule():
    _STATE.update(_util.snapshot())


def tearDownModule():
    _util.restore(_STATE)


class MemoryTestCase(unittest.TestCase):
    """Per-test cleanup for the files a test creates."""

    def _track_topic(self, topic):
        self.addCleanup(config.KNOWLEDGE_DIR.joinpath(f"{topic}.md").unlink, missing_ok=True)

    def _track_experience(self, exp_id):
        self.addCleanup(config.EXPERIENCE_DIR.joinpath(f"{exp_id}.md").unlink, missing_ok=True)

    def _knowledge(self, topic, tags, technique, body="Body."):
        self._track_topic(topic)
        record = save_knowledge.save_knowledge(topic, body, tags=tags, technique=technique)
        self.assertIsNotNone(record)
        return record

    def _rows(self):
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            return {row[0]: row[1:] for row in
                    conn.execute("SELECT path, type, title, tags, technique FROM memories")}
        finally:
            conn.close()


class SearchTests(MemoryTestCase):
    """Targeted retrieval (spec sections 16, 32, 33)."""

    def test_search_ranks_exact_title_first(self):
        self._knowledge("alpha", "alpha", "alpha")
        self._knowledge("beta", "beta", "beta")
        results = search.search("alpha", memory_type="knowledge")
        self.assertEqual([r["path"] for r in results], ["knowledge/alpha.md"])
        self.assertEqual(results[0]["score"], 1.0)

    def test_search_scores_are_graded_by_coverage(self):
        self._knowledge("graded", "one, two", "tech")
        full = search.search("one two", memory_type="knowledge")
        partial = search.search("one three", memory_type="knowledge")
        self.assertEqual(full[0]["path"], "knowledge/graded.md")
        self.assertGreater(full[0]["score"], partial[0]["score"])

    def test_search_filters_by_type_and_limit(self):
        self._knowledge("typed", "typed", "typed")
        self._track_experience("lab-typed")
        save_experience.save_experience("lab-typed", "Typed", "Body.", tags="typed", technique="typed")
        knowledge = search.search("typed", memory_type="knowledge")
        experience = search.search("typed", memory_type="experience")
        self.assertEqual([r["path"] for r in knowledge], ["knowledge/typed.md"])
        self.assertEqual([r["path"] for r in experience], ["experiences/lab-typed.md"])

        for i in range(7):
            self._track_experience(f"lab-lim-{i}")
            save_experience.save_experience(f"lab-lim-{i}", f"Limited {i}", "Body.", tags="limit")
        self.assertEqual(len(search.search("limit", memory_type="experience")), 5)
        self.assertEqual(len(search.search("limit", memory_type="experience", limit=2)), 2)

    def test_search_finds_a_record_by_its_file_name(self):
        # A challenge ID lives in the file name; it must stay searchable so
        # Agent can ask "have I solved this one before?".
        self._track_experience("lab-codename-9001")
        save_experience.save_experience("lab-codename-9001", "Codename", "Body.",
                                        tags="ordinary-tag", technique="plain")
        for query in ("codename", "lab-codename-9001", "9001"):
            hits = search.search(query, memory_type="experience")
            self.assertIn("experiences/lab-codename-9001.md",
                          [r["path"] for r in hits], query)

    def test_search_keeps_exact_title_on_top(self):
        self._track_topic("scorer")
        save_knowledge.save_knowledge("scorer", "Body.", tags="alpha", technique="alpha")
        results = search.search("scorer")
        self.assertEqual(results[0]["path"], "knowledge/scorer.md")
        self.assertEqual(results[0]["score"], 1.0)

    def test_search_empty_query_and_no_match(self):
        self.assertEqual(search.search(""), [])
        self.assertEqual(search.search("zzzznothingmatches"), [])

    def test_invalid_memory_type_is_rejected(self):
        with self.assertRaises(ValueError):
            search.search("x", memory_type="bogus")

    def test_search_skips_rows_whose_file_is_gone(self):
        self._knowledge("ghost", "ghost", "ghost")
        self.assertTrue(search.search("ghost"))
        config.KNOWLEDGE_DIR.joinpath("ghost.md").unlink()
        self.assertEqual(search.search("ghost"), [])

    def test_search_heals_a_deleted_database(self):
        self._knowledge("healed", "healed", "healed")
        config.DATABASE_PATH.unlink(missing_ok=True)
        self.assertFalse(config.DATABASE_PATH.exists())
        results = search.search("healed", memory_type="knowledge")
        self.assertTrue(config.DATABASE_PATH.exists())
        self.assertEqual([r["path"] for r in results], ["knowledge/healed.md"])


class FullTextSearchTests(MemoryTestCase):
    """Matching words that only the body of a memory mentions (spec section 33)."""

    def _lab(self, exp_id, title, tags, technique, body):
        self._track_experience(exp_id)
        record = save_experience.save_experience(exp_id, title, body,
                                                tags=tags, technique=technique)
        self.assertIsNotNone(record)
        return record

    def test_search_finds_a_term_that_only_the_body_mentions(self):
        # Tags are chosen once, when the memory is written. The words that
        # identify the *next* challenge are whatever the target exposes, and
        # those are exactly the words no tag carries.
        self._lab("lab-dom", "DOM XSS", "xss, dom, javascript, web", "xss",
                  "## Challenge Summary\nThe sink is innerHTML fed by location.hash.\n"
                  "A document.write call needed a jQuery hook to reach the flag.")
        for term in ("innerHTML", "location.hash", "document.write", "jQuery"):
            hits = search.search(term, memory_type="experience")
            self.assertIn("experiences/lab-dom.md", [r["path"] for r in hits], term)

    def test_metadata_outranks_a_body_only_match(self):
        self._lab("lab-tagged", "Generic lab", "sql-injection, sqli", "sql-injection",
                  "## Challenge Summary\nNothing about this one.\n")
        self._lab("lab-mentioned", "Web misc", "web, misc", "web",
                  "## Challenge Summary\nThis paragraph mentions sql-injection in passing.\n")
        ranked = [r["path"] for r in search.search("sql injection", memory_type="experience")]
        self.assertEqual(ranked[0], "experiences/lab-tagged.md")
        self.assertEqual(ranked, ["experiences/lab-tagged.md", "experiences/lab-mentioned.md"])
        self.assertGreater(search.search("sql injection", memory_type="experience")[0]["score"],
                           search.search("sql injection", memory_type="experience")[1]["score"])

    def test_full_text_is_capped_below_an_exact_title(self):
        self._knowledge("cap-check", "generic", "generic",
                        "Body repeating cap-check many times: cap-check cap-check cap-check.")
        self.assertLess(search.search("cap check")[0]["score"], 1.0)

    def test_body_changes_are_picked_up_without_a_rebuild(self):
        self._lab("lab-mutable", "Mutable lab", "web", "web", "## Challenge Summary\nOriginal body.\n")
        self.assertEqual(search.search("brandyneuniqueword", memory_type="experience"), [])
        path = config.EXPERIENCE_DIR / "lab-mutable.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nbrandyneuniqueword added.\n",
                        encoding="utf-8")
        path.chmod(0o644)
        self.assertIn("experiences/lab-mutable.md",
                      [r["path"] for r in
                       search.search("brandyneuniqueword", memory_type="experience")])
        config.EXPERIENCE_DIR.joinpath("lab-mutable.md").unlink()
        self.assertEqual(search.search("brandyneuniqueword", memory_type="experience"), [])

    def test_search_never_returns_body_content(self):
        self._lab("lab-secret", "Quiet lab", "quiet", "quiet",
                  "## Challenge Summary\nsupersecretflagvalue only in the body.\n")
        results = search.search("supersecretflagvalue", memory_type="experience")
        self.assertTrue(results)
        for record in results:
            self.assertNotIn("supersecretflagvalue", " ".join(str(v) for v in record.values()))

    def test_undecodable_body_does_not_break_search(self):
        broken = config.KNOWLEDGE_DIR / "broken-body.md"
        broken.write_bytes(b"\xff\xfe\x00bad\xff")
        self.addCleanup(broken.unlink, missing_ok=True)
        self._knowledge("intact", "intact", "intact")
        self.assertTrue(search.search("intact", memory_type="knowledge"))
        self.assertEqual(search.search("bad", memory_type="knowledge"), [])

    def test_a_deleted_memory_does_not_pin_its_cached_tokens(self):
        self._lab("lab-pinned", "Pinned lab", "web", "web", "## Challenge Summary\npinnedword here.\n")
        self.assertTrue(search.search("pinnedword", memory_type="experience"))
        self.assertIn("experiences/lab-pinned.md", search._DOCUMENT_TOKENS)
        config.EXPERIENCE_DIR.joinpath("lab-pinned.md").unlink()
        search._DOCUMENT_TOKENS.pop("experiences/lab-pinned.md")
        search.rebuild()
        self.assertNotIn("experiences/lab-pinned.md", search._DOCUMENT_TOKENS)

    def test_metadata_change_is_reflected_without_a_rebuild(self):
        self._lab("lab-retag", "Retagged lab", "originaltag", "originaltech",
                  "## Challenge Summary\nUnrelated words.\n")
        self.assertTrue(search.search("originaltag", memory_type="experience"))
        path = config.EXPERIENCE_DIR / "lab-retag.md"
        text = (path.read_text(encoding="utf-8")
                .replace("originaltag", "freshtag").replace("originaltech", "freshtech"))
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)
        search.rebuild()
        self.assertEqual(search.search("originaltag", memory_type="experience"), [])
        self.assertTrue(search.search("freshtag", memory_type="experience"))

    def test_catalog_metadata_change_invalidates_cached_tokens(self):
        # memory.db is derived data (spec sections 14, 39), so a catalog can
        # carry metadata that disagrees with an unchanged Markdown file. The
        # file mtime alone would not notice, and the stale tags would keep
        # answering queries.
        #
        # The tags are deliberately absent from the Markdown: every writer
        # also records tags in the file's own Metadata block, so a tag word
        # left in the body would keep matching through full-text and hide
        # which cache produced the hit.
        self._lab("lab-restored", "Restored lab", "alphaword", "betaword",
                  "## Challenge Summary\nUnrelated prose only.\n")
        # Strip the tag words from the file so only the catalog can match them.
        path = config.EXPERIENCE_DIR / "lab-restored.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Tags: alphaword", "Tags:").replace("Technique: betaword", "")
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)
        self.assertTrue(search.search("alphaword", memory_type="experience"))
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            conn.execute("UPDATE memories SET tags = 'gammaword', technique = 'deltaword'"
                         " WHERE path = 'experiences/lab-restored.md'")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(search.search("alphaword", memory_type="experience"), [])
        self.assertTrue(search.search("gammaword", memory_type="experience"))

    def test_a_restored_catalog_replaces_the_file_metadata_in_results(self):
        # rebuild() is what normally reconciles the two. A catalog edited by
        # hand is out of step with the Markdown, so search repairs it before
        # answering and reports the file's view, not the edited row's.
        self._lab("lab-override", "Override lab", "filetag", "filetech",
                  "## Challenge Summary\nProse.\n")
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            conn.execute("UPDATE memories SET tags = 'dbtag' WHERE path = 'experiences/lab-override.md'")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(search.search("filetag", memory_type="experience")[0]["tags"], "filetag")
        self.assertEqual(search.search("dbtag", memory_type="experience"), [])

    def test_tied_scores_are_ordered_most_recently_updated_first(self):
        # Several labs of one class score identically. Ordering those by the
        # catalog id would hand back whichever was written first, so the
        # freshest Experience has to lead instead.
        for index in range(4):
            self._lab(f"lab-order-{index}", f"Shared class lab {index}",
                      "shared-tag", "shared-tech",
                      f"## Challenge Summary\nThe same sharedtext in every lab. Variant {index}.\n")
        ordered = [r["path"] for r in search.search("sharedtext", memory_type="experience")]
        self.assertEqual(ordered, [f"experiences/lab-order-{i}.md" for i in reversed(range(4))])

    def test_a_higher_score_still_beats_a_more_recent_twin(self):
        # Recency only breaks ties; it must not outrank relevance.
        self._lab("lab-old-hit", "Old but tagged", "xss", "xss",
                  "## Challenge Summary\nUnrelated body.\n")
        self._lab("lab-new-miss", "New but incidental", "web", "web",
                  "## Challenge Summary\nMentions xss once in passing.\n")
        ranked = [r["path"] for r in search.search("xss", memory_type="experience")]
        self.assertEqual(ranked[0], "experiences/lab-old-hit.md")

    def test_a_corrupt_database_is_rebuilt_rather_than_raised(self):
        # memory.db is derived data, so garbage in that file must not take
        # search down with it (spec sections 14, 38).
        self._lab("lab-corrupt", "Corrupt lab", "corruptcheck", "corruptcheck",
                  "## Challenge Summary\nBody survives.\n")
        self.assertTrue(search.search("corruptcheck", memory_type="experience"))
        config.DATABASE_PATH.write_bytes(b"this is not a database" * 40)
        results = search.search("corruptcheck", memory_type="experience")
        self.assertEqual([r["path"] for r in results], ["experiences/lab-corrupt.md"])
        self.assertEqual(results[0]["tags"], "corruptcheck")
        self.assertIn("Body survives",
                      search.read("lab-corrupt")["content"])

    def test_an_empty_database_file_is_rebuilt(self):
        self._lab("lab-empty-db", "Empty db lab", "emptydbcheck", "emptydbcheck",
                  "## Challenge Summary\nBody.\n")
        config.DATABASE_PATH.write_bytes(b"")
        self.assertEqual([r["path"] for r in
                          search.search("emptydbcheck", memory_type="experience")],
                         ["experiences/lab-empty-db.md"])

    def test_search_does_not_retokenize_the_same_document(self):
        self._lab("lab-token", "Token lab", "token-tag", "token-tech",
                  "## Challenge Summary\ntokenword body.\n")
        search.search("tokenword", memory_type="experience")
        original = search._tokenize
        calls = []

        def counting(text):
            calls.append(text)
            return original(text)

        search._tokenize = counting
        self.addCleanup(setattr, search, "_tokenize", original)
        search.search("tokenword", memory_type="experience")
        search.search("tokenword", memory_type="experience")
        # Only the query itself should be tokenized; document text comes from
        # the cache keyed on mtime.
        self.assertEqual(len(calls), 2, calls)


class ReadTests(MemoryTestCase):
    """Reading a memory document (spec section 17)."""

    def test_read_accepts_path_topic_and_id(self):
        self._track_topic("forms")
        save_knowledge.save_knowledge("forms", "Body text.", tags="forms")
        content = search.read("forms")["content"]
        self.assertEqual(search.read("forms.md")["content"], content)
        self.assertEqual(search.read("knowledge/forms.md")["content"], content)
        self.assertEqual(search.read("forms")["type"], "knowledge")

        self._track_experience("lab-forms")
        save_experience.save_experience("lab-forms", "Forms", "Experience body.")
        found = search.read("lab-forms")
        self.assertEqual(found["type"], "experience")
        self.assertEqual(found["path"], "experiences/lab-forms.md")
        self.assertIn("Experience body.", found["content"])

    def test_read_missing_and_traversal_are_refused(self):
        self.assertIsNone(search.read("does-not-exist"))
        self.assertIsNone(search.read("../../etc/passwd"))
        self.assertIsNone(search.read("../xss"))
        self.assertIsNone(search.read(""))
        self.assertIsNone(search.read(None))

    def test_read_undecodable_file_returns_none(self):
        broken = config.KNOWLEDGE_DIR / "broken-bytes.md"
        broken.write_bytes(b"\xff\xfe\x00bad\xff")
        self.addCleanup(broken.unlink, missing_ok=True)
        self.assertIsNone(search.read("broken-bytes"))


class SaveKnowledgeTests(MemoryTestCase):
    """Creating a Knowledge topic (spec sections 8, 14, 40)."""

    def test_creates_a_complete_searchable_document(self):
        self._track_topic("xss")
        record = save_knowledge.save_knowledge(
            "xss", "When investigating DOM XSS:\n1. Find the source.\n",
            tags=["xss", "dom-xss"], technique="xss")
        self.assertEqual(record["type"], "knowledge")
        self.assertEqual(record["path"], "knowledge/xss.md")
        document = search.read("xss")["content"]
        self.assertTrue(document.startswith("# xss"))
        self.assertIn("## Metadata", document)
        self.assertIn("Title: xss", document)
        self.assertIn("Tags: xss, dom-xss", document)
        self.assertIn("Technique: xss", document)
        self.assertIn("Find the source", document)

    def test_catalog_row_matches_the_file(self):
        self._track_topic("synced")
        record = save_knowledge.save_knowledge("synced", "Body.", tags="sync-check", technique="sync-check")
        row = self._rows()["knowledge/synced.md"]
        self.assertEqual(row, ("knowledge", "synced", "sync-check", "sync-check"))
        self.assertEqual(record["path"], "knowledge/synced.md")

    def test_refuses_an_existing_topic_without_overwriting(self):
        self._track_topic("kept")
        save_knowledge.save_knowledge("kept", "Original.", tags="keep")
        self.assertIsNone(save_knowledge.save_knowledge("kept", "OVERWRITTEN"))
        self.assertIn("Original.", search.read("kept")["content"])
        self.assertNotIn("OVERWRITTEN", search.read("kept")["content"])
        self.assertEqual(len(list(config.KNOWLEDGE_DIR.glob("kept*.md"))), 1)

    def test_refuses_invalid_input(self):
        self.assertIsNone(save_knowledge.save_knowledge("", "Body."))
        self.assertIsNone(save_knowledge.save_knowledge("x", ""))
        self.assertIsNone(save_knowledge.save_knowledge("../escape", "Body."))
        self.assertIsNone(save_knowledge.save_knowledge("sub/dir", "Body."))
        self.assertIsNone(save_knowledge.save_knowledge(None, "Body."))


class UpdateKnowledgeTests(MemoryTestCase):
    """Updating a Knowledge topic (spec sections 20, 40)."""

    def test_updates_an_existing_topic(self):
        self._track_topic("growing")
        save_knowledge.save_knowledge("growing", "Original.", tags="grow", technique="grow")
        record = update_knowledge.update_knowledge("growing", "Original.\n\n## Lessons\n- lesson one\n",
                                                   tags="grow", technique="grow")
        self.assertIsNotNone(record)
        self.assertEqual(record["path"], "knowledge/growing.md")
        document = search.read("growing")["content"]
        self.assertIn("lesson one", document)
        self.assertIn("Tags: grow", document)

    def test_keeps_the_original_creation_time(self):
        self._track_topic("aged")
        save_knowledge.save_knowledge("aged", "Body.", tags="aged")
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            before = conn.execute(
                "SELECT created_at FROM memories WHERE path = 'knowledge/aged.md'").fetchone()[0]
        finally:
            conn.close()
        update_knowledge.update_knowledge("aged", "Body. More.", tags="aged")
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            after = conn.execute(
                "SELECT created_at FROM memories WHERE path = 'knowledge/aged.md'").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(before, after)

    def test_refuses_a_missing_topic_and_creates_nothing(self):
        self.assertIsNone(update_knowledge.update_knowledge("never-existed", "Body."))
        self.assertFalse(config.KNOWLEDGE_DIR.joinpath("never-existed.md").exists())

    def test_omitted_metadata_is_preserved(self):
        # A revisit must not silently destroy what made an item searchable.
        self._track_topic("preserved")
        save_knowledge.save_knowledge("preserved", "Body.", tags="keepme", technique="keepme")
        record = update_knowledge.update_knowledge("preserved", "Body. More text.")
        self.assertEqual(record["tags"], "keepme")
        self.assertEqual(record["technique"], "keepme")
        self.assertIn("Tags: keepme", search.read("preserved")["content"])
        self.assertTrue(search.search("keepme", memory_type="knowledge"))

        self._track_experience("lab-preserved")
        save_experience.save_experience("lab-preserved", "Preserved", "Body.", tags="keepme")
        record = save_experience.save_experience(
            "lab-preserved", "Preserved revisited", "Updated body.", overwrite=True)
        self.assertEqual(record["tags"], "keepme")
        self.assertTrue(search.search("keepme", memory_type="experience"))

    def test_repeated_updates_never_duplicate_a_topic(self):
        self._track_topic("stable")
        save_knowledge.save_knowledge("stable", "Body.", tags="stable")
        body = "Body."
        for i in range(3):
            # update replaces the body, so the caller accumulates it first
            body += f"\nlesson {i}\n"
            update_knowledge.update_knowledge("stable", body, tags="stable")
        self.assertEqual(len(list(config.KNOWLEDGE_DIR.glob("stable*.md"))), 1)
        document = search.read("stable")["content"]
        for i in range(3):
            self.assertIn(f"lesson {i}", document)


class SaveExperienceTests(MemoryTestCase):
    """Experience storage (spec sections 9, 40)."""

    def test_composes_the_experience_structure(self):
        self._track_experience("lab-500")
        record = save_experience.save_experience(
            "lab-500", "DOM XSS via innerHTML",
            "## Challenge Summary\nA search page reflects input.\n\n"
            "## Successful Approach\nPayload executed.\n\n"
            "## Failed Approaches\n- First attempt failed.\n",
            source="ctf-web", tags=["dom-xss", "innerHTML"], technique="xss",
            challenge_type="web")
        self.assertEqual(record["type"], "experience")
        self.assertEqual(record["path"], "experiences/lab-500.md")
        document = search.read("lab-500")["content"]
        self.assertTrue(document.startswith("# DOM XSS via innerHTML"))
        metadata = document.split("## Metadata", 1)[1]
        positions = [metadata.index(label) for label in
                     ("ID:", "Title:", "Source:", "Type:", "Tags:", "Technique:")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ID: lab-500", metadata)
        self.assertIn("Source: ctf-web", metadata)
        self.assertIn("Type: web", metadata)
        self.assertIn("Tags: dom-xss, innerHTML", metadata)
        for section in ("## Challenge Summary", "## Successful Approach",
                        "## Failed Approaches"):
            self.assertIn(section, document)

    def test_duplicate_id_is_refused_then_overwrite_is_explicit(self):
        self._track_experience("lab-501")
        save_experience.save_experience("lab-501", "First", "First version.")
        self.assertIsNone(save_experience.save_experience("lab-501", "Second", "Second version."))
        self.assertIn("First version.", search.read("lab-501")["content"])

        record = save_experience.save_experience("lab-501", "First revisited", "Updated version.",
                                                overwrite=True)
        self.assertEqual(record["path"], "experiences/lab-501.md")
        self.assertIn("Updated version.", search.read("lab-501")["content"])

    def test_invalid_ids_are_refused(self):
        self.assertIsNone(save_experience.save_experience("", "Title", "Body."))
        self.assertIsNone(save_experience.save_experience("../escape", "Title", "Body."))
        self.assertIsNone(save_experience.save_experience("lab", "Title", ""))

    def test_saved_experience_is_searchable(self):
        self._track_experience("lab-502")
        save_experience.save_experience("lab-502", "Unique Findable Experience", "Body.",
                                        tags="findable-check", technique="findable-check")
        found = search.search("findable-check", memory_type="experience")
        self.assertEqual([r["path"] for r in found], ["experiences/lab-502.md"])


class CatalogTests(MemoryTestCase):
    """The catalog is derived data (spec sections 38, 39)."""

    def test_metadata_cannot_break_out_of_its_line(self):
        # Newlines in metadata must not create a second Metadata section:
        # the file and the catalog row have to keep describing the same thing.
        self._track_topic("injected")
        record = save_knowledge.save_knowledge(
            "injected", "Body.", tags="good\nTags: injected", technique="inj")
        document = search.read("injected")["content"]
        sections = sum(1 for line in document.splitlines() if line.strip().startswith("## "))
        self.assertEqual(sections, 1)          # no second Metadata heading
        self.assertNotIn("\n", record["tags"])  # metadata stays single-line
        search.rebuild()
        rebuilt = search.search("injected", memory_type="knowledge")[0]
        self.assertEqual(rebuilt["tags"], record["tags"])
        self.assertEqual(rebuilt["technique"], record["technique"])

    def test_caller_header_is_not_duplicated(self):
        # A caller that supplies its own '# Title' + '## Metadata' prologue
        # must not produce a file with two titles and two Metadata sections.
        self._track_experience("lab-dupe")
        body = "## Challenge Summary\nBody text.\n\n## Lessons Learned\n- one\n"
        with_header = ("# Supplied Title\n\n## Metadata\n\nID: whatever\n"
                       "Title: Supplied Title\n\n" + body)
        record = save_experience.save_experience(
            "lab-dupe", "Real Title", with_header, tags="dupe")
        self.assertIsNotNone(record)
        document = search.read("lab-dupe")["content"]
        self.assertEqual(document.count("\n# "), 0)
        self.assertEqual(len([l for l in document.splitlines() if l.startswith("# ")]), 1)
        self.assertEqual(document.count("## Metadata"), 1)
        self.assertNotIn("ID: whatever", document)
        # the body survives intact, and the catalog row still matches
        self.assertIn("## Challenge Summary", document)
        self.assertIn("- one", document)
        search.rebuild()
        rebuilt = search.search("dupe", memory_type="experience")[0]
        self.assertEqual(rebuilt["title"], record["title"])
        self.assertEqual(rebuilt["tags"], record["tags"])

    def test_body_only_is_still_accepted(self):
        self._track_topic("plain-body")
        self.assertIsNotNone(
            save_knowledge.save_knowledge("plain-body", "## Section\nText.\n", tags="plain"))
        document = search.read("plain-body")["content"]
        self.assertEqual(document.count("## Metadata"), 1)
        self.assertEqual(len([l for l in document.splitlines() if l.startswith("# ")]), 1)

    def test_written_files_are_readable(self):
        # mkstemp creates 0600; memory files must stay readable.
        self._track_topic("perms")
        save_knowledge.save_knowledge("perms", "Body.")
        mode = config.KNOWLEDGE_DIR.joinpath("perms.md").stat().st_mode
        self.assertEqual(mode & 0o777, 0o644)

    def test_failed_catalog_write_leaves_nothing_behind(self):
        self._track_topic("rolled-back")
        original_store = save_knowledge._store
        try:
            save_knowledge._store = lambda *args, **kwargs: None
            self.assertIsNone(save_knowledge.save_knowledge("rolled-back", "Body.", tags="x"))
        finally:
            save_knowledge._store = original_store
        self.assertIsNone(search.read("rolled-back"))
        self.assertNotIn("knowledge/rolled-back.md",
                         self._rows())  # no phantom record in the catalog

    def test_failed_update_restores_previous_content(self):
        self._track_topic("restore-me")
        save_knowledge.save_knowledge("restore-me", "ORIGINAL BODY", tags="keepme")
        original_store = update_knowledge._store
        try:
            update_knowledge._store = lambda *args, **kwargs: None
            self.assertIsNone(update_knowledge.update_knowledge("restore-me", "CORRUPTED"))
        finally:
            update_knowledge._store = original_store
        document = search.read("restore-me")["content"]
        self.assertIn("ORIGINAL BODY", document)
        self.assertNotIn("CORRUPTED", document)

    def test_rebuild_reindexes_every_file_from_markdown(self):
        self._track_topic("rebuildable")
        save_knowledge.save_knowledge("rebuildable", "Body.", tags="rebuild-check", technique="rebuild-check")
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            conn.execute("UPDATE memories SET path = 'knowledge/wrong.md' "
                         "WHERE path = 'knowledge/rebuildable.md'")
            conn.commit()
        finally:
            conn.close()
        # search() detects the mismatch on its own, so the wrong path is gone
        # before rebuild() is asked for. Check the repair directly as well.
        self.assertEqual(search.rebuild(), 1)
        self.assertNotIn("knowledge/wrong.md", self._rows())
        found = search.search("rebuild-check", memory_type="knowledge")
        self.assertIn("knowledge/rebuildable.md", [r["path"] for r in found])
        row = self._rows()["knowledge/rebuildable.md"]
        self.assertEqual(row, ("knowledge", "rebuildable", "rebuild-check", "rebuild-check"))

    def test_search_repairs_a_catalog_that_lost_rows(self):
        # Losing the catalog and then writing a new memory recreates it with
        # one row. That looks healthy, so an emptiness check would not notice
        # that every other memory has dropped out of search.
        self._track_topic("first")
        save_knowledge.save_knowledge("first", "First body.", tags="firstcheck")
        config.DATABASE_PATH.unlink()
        self._track_experience("second")
        save_experience.save_experience("second", "Second", "Second body.", tags="secondcheck")

        self.assertEqual(search.search("firstcheck", memory_type="knowledge")[0]["path"],
                         "knowledge/first.md")
        self.assertEqual(sorted(self._rows()), ["experiences/second.md", "knowledge/first.md"])

    def test_search_indexes_a_file_the_catalog_never_saw(self):
        self._track_topic("seed")
        save_knowledge.save_knowledge("seed", "Body.", tags="seedcheck")
        self._track_topic("orphan")
        orphan = config.KNOWLEDGE_DIR / "orphan.md"
        orphan.write_text("# orphan\n\n## Metadata\n\nTitle: orphan\nTags: orphancheck\n",
                          encoding="utf-8")
        orphan.chmod(0o644)
        self.assertEqual([r["path"] for r in
                          search.search("orphancheck", memory_type="knowledge")],
                         ["knowledge/orphan.md"])

    def test_search_drops_a_catalog_row_with_no_file_behind_it(self):
        self._track_topic("real")
        save_knowledge.save_knowledge("real", "Body.", tags="realcheck")
        conn = sqlite3.connect(config.DATABASE_PATH)
        try:
            conn.execute("INSERT INTO memories (type, title, path, tags, technique,"
                         " created_at, updated_at) VALUES"
                         " ('knowledge', 'ghost', 'knowledge/ghost.md', 'ghostcheck',"
                         "  'ghost', 'x', 'x')")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(search.search("ghostcheck"), [])
        self.assertNotIn("knowledge/ghost.md", self._rows())

    def test_rebuild_skips_undecodable_files(self):
        # Seed a valid file so the assertion does not depend on whatever memory
        # the repository happens to ship.
        self._track_topic("decodable")
        save_knowledge.save_knowledge("decodable", "Body.", tags="decode-check")
        broken = config.KNOWLEDGE_DIR / "broken-rebuild.md"
        broken.write_bytes(b"\xff\xfe\x00bad\xff")
        self.addCleanup(broken.unlink, missing_ok=True)
        self.assertGreaterEqual(search.rebuild(), 1)
        self.assertNotIn("knowledge/broken-rebuild.md", self._rows())
        self.assertIn("knowledge/decodable.md", self._rows())


if __name__ == "__main__":
    unittest.main()