import codecs
import re
from pathlib import Path
from typing import List, Tuple


# Ported from ystyle/kaf-cli defaults:
# https://github.com/ystyle/kaf-cli/blob/master/internal/model/book.go
KAF_DEFAULT_MATCH = (
    r"^第[0-9一二三四五六七八九十零〇百千两 ]+[章回节集幕卷部]"
    r"|^[Ss]ection.{1,20}$"
    r"|^[Cc]hapter.{1,20}$"
    r"|^[Pp]age.{1,20}$"
    r"|^\d{1,4}$"
    r"|^\d+、$"
    r"|^引子$"
    r"|^楔子$"
    r"|^章节目录"
    r"|^章节"
    r"|^序章"
    r"|^最终章 \w{1,20}$"
    r"|^番外\d?\w{0,20}"
    r"|^完本感言.{0,4}$"
)
KAF_VOLUME_MATCH = r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部]"
KAF_DEFAULT_EXCLUSION = r"^第[0-9一二三四五六七八九十零〇百千两 ]+(部门|部队|部属|部分|部件|部落|部.*：$)"

EXTRA_CHAPTER_MATCH = (
    r"^第\s*[0-9０-９零〇○一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟萬 ]+"
    r"\s*[章节回卷集幕部篇]\s*(?:[：:、.\s-].*)?$"
)


def try_encodings(file_path, encodings=None) -> str:
    """Try common TXT encodings; kaf-cli similarly auto-detects Chinese TXT files."""
    if encodings is None:
        encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16", "utf-16-le", "utf-16-be"]

    file_path = Path(file_path)
    for encoding in encodings:
        try:
            with codecs.open(file_path, "r", encoding=encoding) as file:
                file.read(4096)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    import locale

    return locale.getpreferredencoding(False)


def normalize_title_line(line: str) -> str:
    return line.strip().lstrip("\ufeff").replace("\u3000", " ").strip()


def compile_regex(pattern: str | None, fallback: str) -> re.Pattern:
    return re.compile(pattern or fallback)


def is_kaf_chapter_title(
    line: str,
    chapter_regex: re.Pattern,
    volume_regex: re.Pattern,
    exclusion_regex: re.Pattern | None,
    max_title_chars: int,
) -> bool:
    title = normalize_title_line(line)
    if not title or len(title) > max_title_chars:
        return False
    if exclusion_regex and exclusion_regex.search(title):
        return False
    return bool(chapter_regex.search(title) or volume_regex.search(title) or re.search(EXTRA_CHAPTER_MATCH, title))


def split_novel_to_chapters(
    file_path: str,
    pattern: str | None = None,
    volume_pattern: str | None = KAF_VOLUME_MATCH,
    exclusion_pattern: str | None = KAF_DEFAULT_EXCLUSION,
    max_title_chars: int = 35,
) -> List[Tuple[str, str]]:
    """
    Split TXT novel using kaf-cli-style chapter recognition.

    kaf-cli's parser identifies chapter titles by a default regex, optional
    volume regex, exclusion regex, and max title length. This function keeps
    that recognition behavior but returns plain text chapters for our database.
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    encoding = try_encodings(file_path)
    print(f"使用编码: {encoding}")

    chapter_regex = compile_regex(pattern, KAF_DEFAULT_MATCH)
    volume_regex = compile_regex(volume_pattern, KAF_VOLUME_MATCH) if volume_pattern != "false" else re.compile(r"a^")
    exclusion_regex = re.compile(exclusion_pattern) if exclusion_pattern and exclusion_pattern != "false" else None

    chapters: List[Tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    leading_lines: list[str] = []

    with open(file_path, "r", encoding=encoding, errors="replace") as file:
        for raw_line in file:
            line = raw_line.rstrip("\r\n")
            normalized = normalize_title_line(line)
            if is_kaf_chapter_title(normalized, chapter_regex, volume_regex, exclusion_regex, max_title_chars):
                if current_title or current_lines:
                    title = current_title or "章节正文"
                    content = "\n".join([title, *current_lines]).strip()
                    chapters.append((title, content))
                current_title = normalized
                current_lines = []
                continue

            if current_title:
                current_lines.append(line)
            elif normalized:
                leading_lines.append(line)

    if current_title or current_lines:
        title = current_title or "章节正文"
        content = "\n".join([title, *current_lines]).strip()
        chapters.append((title, content))
    elif not chapters and leading_lines:
        title = "章节正文"
        content = "\n".join([title, *leading_lines]).strip()
        chapters.append((title, content))

    return chapters
