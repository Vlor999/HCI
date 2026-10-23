"""Tests for hci.documents: parsing each format, segmentation and packing, and skipping unreadable files."""

import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import docx
import pytest
from loguru import logger
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from hci import documents
from hci.config import get_settings
from hci.constants import Source
from hci.types import DocumentSection


@pytest.fixture
def docs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty documents folder, set as `documents_dir`."""
    path = tmp_path / "documents"
    path.mkdir()
    monkeypatch.setenv("HCI_DOCUMENTS_DIR", str(path))
    get_settings.cache_clear()
    return path


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Loguru warnings emitted during the test."""
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")
    yield messages
    logger.remove(sink)


def _make_pdf(path: Path, pages: list[str]) -> Path:
    """A PDF with one line of Helvetica text per page."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(612, 792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
    return path


def _make_docx(path: Path, blocks: list[tuple[str, str]]) -> Path:
    """A DOCX of `(style, text)` paragraphs."""
    document = docx.Document()
    for style, text in blocks:
        document.add_paragraph(text, style=style)
    document.save(str(path))
    return path


def _texts(path: Path) -> list[str]:
    return [c.text for c in documents.load_document(path)]


class TestPack:
    def test_short_paragraphs_share_one_chunk(self):
        """Paragraphs that fit together make a single chunk."""
        # Act / Assert
        assert documents.pack(["One two.", "Three four."], limit=10, overlap=2) == ["One two. Three four."]

    def test_cuts_between_sentences_with_overlap(self):
        """A long section is cut between sentences; the next chunk repeats the last sentence fitting the overlap."""
        # Arrange
        paragraph = "Alpha beta gamma. Delta epsilon. Zeta eta theta."
        # Act
        chunks = documents.pack([paragraph], limit=5, overlap=2)
        # Assert
        assert chunks == ["Alpha beta gamma. Delta epsilon.", "Delta epsilon. Zeta eta theta."]

    def test_sentence_longer_than_a_chunk_is_cut_by_words(self):
        """Only a sentence longer than a chunk on its own is cut mid-sentence."""
        # Act
        chunks = documents.pack(["a b c d e f g"], limit=3, overlap=0)
        # Assert
        assert chunks == ["a b c", "d e f", "g"]

    def test_chunks_stay_within_limit(self):
        """No chunk exceeds the word limit, overlap included."""
        # Arrange
        paragraphs = [" ".join(f"w{i}{j}" for j in range(7)) + "." for i in range(30)]
        # Act
        chunks = documents.pack(paragraphs, limit=20, overlap=8)
        # Assert
        assert max(len(c.split()) for c in chunks) <= 20


class TestFormats:
    def test_markdown_section_title_is_heading_path(self, docs_dir: Path):
        """Each Markdown section is a chunk headed by file name and heading path, id `<ref>#<n>`."""
        # Arrange
        path = docs_dir / "guide.md"
        path.write_text("# Guide\n\nIntro.\n\n## Safety\n\nStop on ice.\n\n# Other\n\nEnd.")
        # Act
        chunks = documents.load_document(path)
        # Assert
        assert [c.text for c in chunks] == [
            "guide.md, Guide: Intro.",
            "guide.md, Guide > Safety: Stop on ice.",
            "guide.md, Other: End.",
        ]
        assert chunks[1].id == f"{path.as_posix()}#2"
        assert chunks[1].source == Source.DOCUMENT

    def test_text_paragraphs_split_on_blank_lines(self, docs_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """A text file is cut between blank-line paragraphs when they do not fit together."""
        # Arrange
        monkeypatch.setenv("HCI_CHUNK_WORDS", "4")
        monkeypatch.setenv("HCI_CHUNK_OVERLAP_WORDS", "0")
        get_settings.cache_clear()
        path = docs_dir / "notes.txt"
        path.write_text("Rain on\npath A.\n\nPath B dry.")
        # Act / Assert
        assert _texts(path) == ["notes.txt: Rain on path A.", "notes.txt: Path B dry."]

    def test_docx_headings_come_from_styles(self, docs_dir: Path):
        """DOCX `Heading <n>` paragraphs title the sections of the body paragraphs below them."""
        # Arrange
        path = _make_docx(
            docs_dir / "report.docx",
            [("Heading 1", "Trails"), ("Normal", "Path C is paved."), ("Heading 2", "Winter"), ("Normal", "Icy.")],
        )
        # Act / Assert
        assert _texts(path) == ["report.docx, Trails: Path C is paved.", "report.docx, Trails > Winter: Icy."]

    def test_pdf_chunks_keep_the_page(self, docs_dir: Path):
        """PDF chunks are cut per page and headed by the page number."""
        # Arrange
        path = _make_pdf(docs_dir / "log.pdf", ["Bridge closed.", "Ford is shallow."])
        # Act / Assert
        assert _texts(path) == ["log.pdf, page 1: Bridge closed.", "log.pdf, page 2: Ford is shallow."]

    def test_ligatures_become_letters(self, docs_dir: Path):
        """Ligatures, as PDF exports often produce, are normalised so `floods` matches `ﬂoods`."""
        # Arrange
        path = docs_dir / "notes.txt"
        path.write_text("Path Q \ufb02oods.")
        # Act / Assert
        assert _texts(path) == ["notes.txt: Path Q floods."]


class TestPages:
    def test_exported_pdf_is_indexed(self, docs_dir: Path, tmp_path: Path):
        """A `.pages` file is indexed through the PDF the Pages exporter writes."""
        # Arrange
        path = docs_dir / "plan.pages"
        path.write_bytes(b"zip")
        pdf = _make_pdf(tmp_path / "exported.pdf", ["Charge before noon."])
        # Act
        with patch("hci.documents.export_pages", return_value=pdf) as export:
            texts = _texts(path)
        # Assert
        assert texts == ["plan.pages, page 1: Charge before noon."]
        assert export.call_args.args[0] == path

    def test_failed_export_gives_no_chunks(self, docs_dir: Path):
        """When Pages cannot export the file, it is skipped."""
        # Arrange
        path = docs_dir / "plan.pages"
        path.write_bytes(b"zip")
        # Act / Assert
        with patch("hci.documents.export_pages", return_value=None):
            assert _texts(path) == []

    def test_without_osascript_warns_to_export(self, tmp_path: Path, warnings: list[str]):
        """Off macOS the exporter returns None and the warning says to export as PDF or DOCX."""
        # Act
        with patch("hci.documents.shutil.which", return_value=None):
            result = documents.export_pages(tmp_path / "plan.pages", tmp_path / "plan.pdf")
        # Assert
        assert result is None
        assert "PDF or DOCX" in warnings[0]

    def test_export_runs_pages_through_osascript(self, tmp_path: Path):
        """The exporter passes the paths to the AppleScript as arguments."""
        # Arrange
        source, target = tmp_path / "plan.pages", tmp_path / "plan.pdf"
        # Act
        with (
            patch("hci.documents.shutil.which", return_value="/usr/bin/osascript"),
            patch("hci.documents.subprocess.run") as run,
        ):
            result = documents.export_pages(source, target)
        # Assert
        assert result == target
        assert run.call_args.args[0][0] == "osascript"
        assert run.call_args.args[0][-2:] == [str(source.resolve()), str(target)]

    def test_export_failure_warns(self, tmp_path: Path, warnings: list[str]):
        """A failing Pages export returns None with a warning instead of raising."""
        # Act
        with (
            patch("hci.documents.shutil.which", return_value="/usr/bin/osascript"),
            patch("hci.documents.subprocess.run", side_effect=subprocess.CalledProcessError(1, "osascript")),
        ):
            result = documents.export_pages(tmp_path / "plan.pages", tmp_path / "plan.pdf")
        # Assert
        assert result is None
        assert "PDF or DOCX" in warnings[0]


class TestLoadDocuments:
    def test_broken_file_is_skipped_with_warning(self, docs_dir: Path, warnings: list[str]):
        """A file that fails to parse is skipped and the other documents still load."""
        # Arrange
        (docs_dir / "broken.pdf").write_bytes(b"not a pdf")
        (docs_dir / "ok.md").write_text("Fine.")
        # Act
        chunks = documents.load_documents()
        # Assert
        assert [c.text for c in chunks] == ["ok.md: Fine."]
        assert any("broken.pdf" in w for w in warnings)

    def test_reads_subfolders_and_skips_hidden_and_unsupported(self, docs_dir: Path):
        """Supported files are found recursively; hidden files, hidden folders and other types are left out."""
        # Arrange
        for name in ("a.md", "uploads/b.txt", ".hidden.md", ".git/c.md", "image.png"):
            (docs_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (docs_dir / name).write_text("Text.")
        # Act
        files = documents.document_files()
        # Assert
        assert [f.relative_to(docs_dir).as_posix() for f in files] == ["a.md", "uploads/b.txt"]


class TestBounds:
    @pytest.fixture
    def limits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tiny bounds: 10 characters, 1 PDF page, 10 KB of expanded DOCX."""
        monkeypatch.setenv("HCI_MAX_DOCUMENT_CHARS", "10")
        monkeypatch.setenv("HCI_MAX_PDF_PAGES", "1")
        monkeypatch.setenv("HCI_MAX_DOCX_EXPANDED_MB", "0.01")
        get_settings.cache_clear()

    def _make_large_text(self, docs_dir: Path) -> Path:
        path = docs_dir / "long.txt"
        path.write_text("Far more than ten characters.")
        return path

    def _make_two_page_pdf(self, docs_dir: Path) -> Path:
        return _make_pdf(docs_dir / "two.pdf", ["A.", "B."])

    def _make_docx_bomb(self, docs_dir: Path) -> Path:
        return _make_docx(docs_dir / "big.docx", [("Normal", "x")])  # the template alone expands past 10 KB

    @pytest.mark.parametrize(
        ("make", "setting"),
        [
            (_make_large_text, "HCI_MAX_DOCUMENT_CHARS"),
            (_make_two_page_pdf, "HCI_MAX_PDF_PAGES"),
            (_make_docx_bomb, "HCI_MAX_DOCX_EXPANDED_MB"),
        ],
        ids=["text-chars", "pdf-pages", "docx-expanded"],
    )
    def test_over_a_bound_is_skipped_with_reason(self, docs_dir: Path, limits: None, make, setting: str):
        """A document over a size bound gives no chunks, and the reason names the setting."""
        # Arrange
        path = make(self, docs_dir)
        # Act
        chunks = documents.load_document(path)
        # Assert
        assert chunks == []
        assert setting in (documents.document_error(path) or "")


class TestCache:
    def test_unchanged_file_is_parsed_once(self, docs_dir: Path):
        """A second full load reuses the chunks of a file that did not change."""
        # Arrange
        (docs_dir / "a.md").write_text("Text.")
        parser = MagicMock(return_value=[DocumentSection("", ["Text."])])
        # Act
        with patch.dict(documents.PARSERS, {".md": parser}):
            first, second = documents.load_documents(), documents.load_documents()
        # Assert
        assert first == second
        assert parser.call_count == 1

    def test_changed_file_is_parsed_again(self, docs_dir: Path):
        """Editing a file invalidates its cached chunks."""
        # Arrange
        path = docs_dir / "a.md"
        path.write_text("Old.")
        documents.load_documents()
        path.write_text("New text.")
        # Act
        texts = [c.text for c in documents.load_documents()]
        # Assert
        assert texts == ["a.md: New text."]

    def test_failed_pages_export_is_not_retried(self, docs_dir: Path):
        """A `.pages` file that Pages cannot export is tried once per version, not at every reload."""
        # Arrange
        (docs_dir / "plan.pages").write_bytes(b"zip")
        # Act
        with patch("hci.documents.export_pages", return_value=None) as export:
            documents.load_documents()
            documents.load_documents()
        # Assert
        assert export.call_count == 1
        assert "PDF or DOCX" in (documents.document_error(docs_dir / "plan.pages") or "")


def test_file_ref_is_relative_to_repo_root():
    """Files of the repo are referenced by their path from the repo root."""
    # Act / Assert
    assert documents.file_ref(documents.ROOT_DIR / "data" / "paths.json") == "data/paths.json"


def test_overlap_must_be_below_chunk_size(monkeypatch: pytest.MonkeyPatch):
    """Settings refuse an overlap as large as the chunk."""
    # Arrange
    monkeypatch.setenv("HCI_CHUNK_WORDS", "40")
    monkeypatch.setenv("HCI_CHUNK_OVERLAP_WORDS", "40")
    get_settings.cache_clear()
    # Act / Assert
    with pytest.raises(ValueError, match="chunk_overlap_words"):
        get_settings()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("../../x.md", "x.md"), ("..\\..\\x.md", "x.md"), (".env.md", "env.md"), ("my notes;rm.md", "my_notes_rm.md")],
    ids=["posix-traversal", "windows-traversal", "hidden", "odd-characters"],
)
def test_safe_name(filename: str, expected: str):
    """Client file names lose folders, leading dots and characters outside word, `.` and `-`."""
    # Act / Assert
    assert documents.safe_name(filename) == expected
