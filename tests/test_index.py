"""Tests for hci.index: BM25, reciprocal rank fusion and the skip list."""

from hci.constants import Source
from hci.index import HybridIndex
from hci.types import Embed, RecordChunk


def _make_chunk(id: str, text: str) -> RecordChunk:
    return RecordChunk(id, text, Source.DOCUMENT)


def _make_index(embed: Embed) -> HybridIndex:
    return HybridIndex(
        [
            _make_chunk("battery", "battery recharge at the station"),
            _make_chunk("mud", "mud slows the wheels on path A"),
            _make_chunk("snow", "snow covers path P in winter"),
        ],
        embed,
    )


class TestHybridIndex:
    def test_bm25_scores_only_matching_chunks(self, fake_embed):
        """BM25 gives a positive score to chunks sharing a query term, zero to the others."""
        # Arrange
        index = _make_index(fake_embed)
        # Act
        scores = index.bm25("battery recharge")
        # Assert
        assert scores[0] > 0
        assert list(scores[1:]) == [0, 0]

    def test_bm25_ignores_unknown_terms(self, fake_embed):
        """A query with no indexed term scores every chunk zero instead of failing."""
        # Act
        scores = _make_index(fake_embed).bm25("zeppelin")
        # Assert
        assert not scores.any()

    def test_search_ranks_matching_chunk_first(self, fake_embed):
        """The chunk both retrievers agree on comes first after fusion."""
        # Act
        hits = _make_index(fake_embed).search("snow in winter", k=3)
        # Assert
        assert [c.id for c in hits][0] == "snow"

    def test_search_respects_k(self, fake_embed):
        """At most `k` chunks come back."""
        # Act
        hits = _make_index(fake_embed).search("path", k=2)
        # Assert
        assert len(hits) == 2

    def test_search_leaves_out_skipped_ids(self, fake_embed):
        """Skipped ids never appear, even when they match best."""
        # Act
        hits = _make_index(fake_embed).search("snow in winter", k=3, skip={"snow"})
        # Assert
        assert "snow" not in [c.id for c in hits]
        assert len(hits) == 2
