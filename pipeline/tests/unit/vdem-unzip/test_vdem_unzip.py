"""
Unit tests for the V-Dem unzip Lambda (#494 step 5).

The Lambda's job is small + well-defined: receive an SF event with a
ZIP S3 key, extract the largest .csv from the ZIP, upload the CSV to
vdem-staging/unzipped/, return the unzipped key for the next SF state.

Tests use in-memory ZIPs built with `zipfile` and a mocked boto3 S3
client. No real AWS calls.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_LAMBDA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "lambdas" / "vdem-unzip" / "lambda_function.py"


@pytest.fixture(scope="module")
def lambda_module():
    """Load lambda_function.py as a module without invoking the handler."""
    spec = importlib.util.spec_from_file_location("vdem_unzip_under_test", str(_LAMBDA_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_zip(files: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP from a {filename: bytes} map."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------- #
# Happy path                                                             #
# ---------------------------------------------------------------------- #


def test_handler_extracts_largest_csv_and_returns_unzipped_key(lambda_module):
    """Standard V-Dem ZIP contents: one big CSV + a small PDF + a
    README. Lambda picks the CSV, uploads to vdem-staging/unzipped/,
    returns the right contract."""
    csv_data = b"country_text_id,year,v2x_polyarchy\nUSA,2020,0.8\n" * 1000
    zip_bytes = _build_zip(
        {
            "V-Dem-CY-Full+Others-v15.csv": csv_data,
            "Codebook.pdf": b"%PDF-1.4 (fake)" * 100,
            "README.txt": b"V-Dem v15 release notes",
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {
                "bucket": "qgi-data-lake-x",
                "incoming_key": "vdem-staging/incoming/V-Dem-CY-Full+Others-v15.zip",
            },
            None,
        )

    assert result == {
        "bucket": "qgi-data-lake-x",
        "unzipped_key": "vdem-staging/unzipped/V-Dem-CY-Full+Others-v15.csv",
        "csv_size_bytes": len(csv_data),
        "csv_filename": "V-Dem-CY-Full+Others-v15.csv",
    }
    # Verify boto3 calls
    fake_s3.get_object.assert_called_once_with(
        Bucket="qgi-data-lake-x",
        Key="vdem-staging/incoming/V-Dem-CY-Full+Others-v15.zip",
    )
    fake_s3.put_object.assert_called_once()
    put_kwargs = fake_s3.put_object.call_args.kwargs
    assert put_kwargs["Bucket"] == "qgi-data-lake-x"
    assert put_kwargs["Key"] == "vdem-staging/unzipped/V-Dem-CY-Full+Others-v15.csv"
    assert put_kwargs["Body"] == csv_data
    assert put_kwargs["ContentType"] == "text/csv"


def test_handler_picks_largest_when_multiple_csvs(lambda_module):
    """If a ZIP contains 2+ CSVs, pick the largest (the data CSV).
    Locks the contract that downstream gets the data, not metadata."""
    big_csv = b"x" * 10_000
    small_csv = b"y" * 100
    zip_bytes = _build_zip(
        {
            "metadata.csv": small_csv,
            "V-Dem-data.csv": big_csv,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    assert result["csv_filename"] == "V-Dem-data.csv"
    assert result["csv_size_bytes"] == len(big_csv)


def test_handler_strips_directory_prefix_from_zip_member(lambda_module):
    """V-Dem ZIPs often have a top-level directory:
       V-Dem-CY-Full+Others-v15/V-Dem-CY-Full+Others-v15.csv
    The Lambda must strip the directory and use just the basename
    for the unzipped key — otherwise downstream gets a nested path."""
    csv_data = b"data" * 100
    zip_bytes = _build_zip(
        {
            "V-Dem-CY-Full+Others-v15/V-Dem-CY-Full+Others-v15.csv": csv_data,
            "V-Dem-CY-Full+Others-v15/Codebook.pdf": b"pdf" * 50,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # Filename in result is basename only (no directory prefix)
    assert result["csv_filename"] == "V-Dem-CY-Full+Others-v15.csv"
    assert result["unzipped_key"] == ("vdem-staging/unzipped/V-Dem-CY-Full+Others-v15.csv")


def test_handler_case_insensitive_csv_extension(lambda_module):
    """`.CSV` (uppercase) should also match. V-Dem in practice uses
    lowercase `.csv` but defensive against future variation."""
    zip_bytes = _build_zip(
        {
            "data.CSV": b"x" * 1000,
            "Codebook.pdf": b"pdf",
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    assert result["csv_filename"] == "data.CSV"


# ---------------------------------------------------------------------- #
# Error paths                                                            #
# ---------------------------------------------------------------------- #


def test_handler_raises_on_missing_bucket(lambda_module):
    with pytest.raises(lambda_module.UnzipError) as excinfo:
        lambda_module.lambda_handler(
            {"incoming_key": "in.zip"},
            None,
        )
    assert "bucket" in str(excinfo.value)


def test_handler_raises_on_missing_incoming_key(lambda_module):
    with pytest.raises(lambda_module.UnzipError) as excinfo:
        lambda_module.lambda_handler(
            {"bucket": "b"},
            None,
        )
    assert "incoming_key" in str(excinfo.value)


def test_handler_raises_on_empty_event(lambda_module):
    with pytest.raises(lambda_module.UnzipError):
        lambda_module.lambda_handler({}, None)


def test_handler_raises_when_no_csv_in_zip(lambda_module):
    """ZIP has no .csv → raise UnzipError. This is a real upload error
    (operator dropped the wrong file) and must not silently no-op."""
    zip_bytes = _build_zip(
        {
            "Codebook.pdf": b"pdf" * 100,
            "README.txt": b"notes",
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "b", "incoming_key": "in.zip"},
                None,
            )
    err = str(excinfo.value).lower()
    # Post-hardening (PR #9 review item 3) the empty-CSV filter
    # changed the wording from "no .csv files found" to
    # "no non-empty .csv files found" — both forms acceptable.
    assert "non-empty .csv files found" in err or "no .csv" in err
    # Helpful: lists what WAS in the ZIP so the operator can see what
    # got uploaded by mistake
    err_msg = str(excinfo.value)
    assert "Codebook.pdf" in err_msg or "README.txt" in err_msg


def test_handler_raises_on_corrupt_zip(lambda_module):
    """Bad ZIP bytes → UnzipError, not a stack trace into BadZipFile."""
    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(b"not-a-zip")}

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "b", "incoming_key": "in.zip"},
                None,
            )
    assert "invalid ZIP" in str(excinfo.value)


def test_handler_raises_on_s3_get_failure(lambda_module):
    """boto3 get_object raise → UnzipError with the S3 path in the message."""
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = RuntimeError("AccessDenied")

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "qgi-data-lake-x", "incoming_key": "vdem-staging/incoming/v15.zip"},
                None,
            )
    err = str(excinfo.value)
    assert "S3 GetObject failed" in err
    assert "qgi-data-lake-x" in err
    assert "vdem-staging/incoming/v15.zip" in err


def test_handler_raises_on_s3_put_failure(lambda_module):
    """boto3 put_object raise → UnzipError. Operator must know the
    upload step failed (vs the download step)."""
    csv_data = b"x" * 1000
    zip_bytes = _build_zip({"data.csv": csv_data})

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}
    fake_s3.put_object.side_effect = RuntimeError("AccessDenied")

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "qgi-data-lake-x", "incoming_key": "in.zip"},
                None,
            )
    err = str(excinfo.value)
    assert "S3 PutObject failed" in err
    # Distinguishes Get from Put — important for operator triage
    assert "S3 GetObject failed" not in err


# ---------------------------------------------------------------------- #
# Edge cases                                                             #
# ---------------------------------------------------------------------- #


def test_handler_skips_directory_entries(lambda_module):
    """A ZIP can have explicit directory entries with .csv-like names
    (e.g., `data.csv/`). They have `is_dir()` true and should not be
    treated as data files."""
    # Manually craft a ZIP with a directory entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Directory entry first
        info = zipfile.ZipInfo("data.csv/")
        info.external_attr = 0o40755 << 16  # directory bits
        zf.writestr(info, b"")
        # Real file
        zf.writestr("real-data.csv", b"x" * 500)

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(buf.getvalue())}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    assert result["csv_filename"] == "real-data.csv"


def test_handler_returns_csv_size_in_bytes_not_compressed(lambda_module):
    """csv_size_bytes is the UNCOMPRESSED size — that's the size the
    downstream Batch container will see when it downloads from
    vdem-staging/unzipped/. (V-Dem v16: ~388MB uncompressed,
    ~140MB in the ZIP.)"""
    csv_data = b"a" * 100_000  # very compressible content
    zip_bytes = _build_zip({"data.csv": csv_data})

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # Compressed size of `b"a" * 100_000` is tiny (deflate is great on
    # repeated bytes). Uncompressed size must be 100_000.
    assert result["csv_size_bytes"] == 100_000
    assert len(zip_bytes) < 1000  # confirm the ZIP IS heavily compressed


def test_handler_overwrites_existing_unzipped_key(lambda_module):
    """If the same ZIP is uploaded twice (operator re-drops a corrected
    copy), the unzipped key is overwritten. boto3 put_object overwrites
    by default; we just need to confirm we DO call put_object regardless
    of any "exists" checks (we don't have any)."""
    zip_bytes = _build_zip({"data.csv": b"new content"})

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # No head_object / list_objects "does it exist?" pre-check — pure
    # PUT semantics, idempotent on re-runs
    assert not any(c for c in fake_s3.method_calls if c[0] in ("head_object", "list_objects_v2"))
    fake_s3.put_object.assert_called_once()


def test_handler_unzipped_prefix_constant(lambda_module):
    """The unzipped key prefix is exactly `vdem-staging/unzipped/`
    (mirrors the incoming `vdem-staging/incoming/` from the upload
    side). Pin the constant so a refactor doesn't silently break the
    Step Functions definition's path expectation."""
    assert lambda_module.UNZIPPED_PREFIX == "vdem-staging/unzipped/"


# ---------------------------------------------------------------------- #
# PR #9 review hardening                                                 #
# ---------------------------------------------------------------------- #


def test_handler_skips_empty_csv(lambda_module):
    """Review item 3: a 0-byte CSV would silently pass into a corrupt
    downstream ingest. Filter must skip empty CSVs entirely so the
    largest-CSV picker doesn't pick them."""
    zip_bytes = _build_zip(
        {
            "empty.csv": b"",  # 0 bytes — must be skipped
            "real-data.csv": b"y,2020,0.8\n" * 200,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # Empty CSV is invisible to the picker; the real CSV wins
    assert result["csv_filename"] == "real-data.csv"
    assert result["csv_size_bytes"] > 0


def test_handler_raises_when_only_empty_csvs(lambda_module):
    """If every CSV in the ZIP is empty, treat it as a no-CSV upload
    error — not "happy-path with 0 bytes"."""
    zip_bytes = _build_zip(
        {
            "empty1.csv": b"",
            "empty2.csv": b"",
            "Codebook.pdf": b"pdf" * 100,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "b", "incoming_key": "in.zip"},
                None,
            )
    # "non-empty" in the message lets operators distinguish this from
    # the no-CSV-at-all case
    assert "non-empty" in str(excinfo.value).lower()


def test_handler_raises_above_size_cap(lambda_module, monkeypatch):
    """Review item 1: a CSV bigger than MAX_CSV_BYTES raises an
    actionable error instead of silently OOM-ing the Lambda at runtime."""
    # Set a tiny cap so a small ZIP exercises the limit
    monkeypatch.setattr(lambda_module, "MAX_CSV_BYTES", 1000)
    zip_bytes = _build_zip({"data.csv": b"x" * 5000})  # 5000 > 1000

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "b", "incoming_key": "in.zip"},
                None,
            )
    err = str(excinfo.value)
    assert "above the cap" in err
    assert "5,000" in err
    assert "1,000" in err
    # Operator gets the remediation in the message
    assert "MAX_CSV_BYTES" in err


def test_handler_size_cap_default_is_700mb(lambda_module):
    """Pin the default cap so a future refactor doesn't silently
    drop the safety net."""
    assert lambda_module.MAX_CSV_BYTES == 700_000_000


def test_handler_strips_relative_traversal_to_safe_basename(lambda_module):
    """Review item 2 (forward-slash case): `../../evil.csv` after
    split('/') has basename `evil.csv`. The split-then-strip yields
    a safe filename — confirm it gets uploaded under the unzipped/
    prefix, NOT escaped to a parent path. (The forward-slash form
    happens to be self-defending; the regex catches the more
    dangerous unsafe-char and backslash forms below.)"""
    zip_bytes = _build_zip(
        {
            "../../evil.csv": b"x" * 500,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # Basename `evil.csv` is safe → uploaded under unzipped/ prefix
    assert result["csv_filename"] == "evil.csv"
    assert result["unzipped_key"] == "vdem-staging/unzipped/evil.csv"
    # Critically: NOT escaped to `../../evil.csv`
    assert ".." not in result["unzipped_key"]


def test_handler_rejects_unsafe_filename_chars(lambda_module):
    """Review item 2: filenames with unsafe characters (spaces, control
    chars, shell metacharacters, non-ASCII) are rejected by the regex.
    Allowed: ASCII letters/digits/. _ + -"""
    zip_bytes = _build_zip(
        {
            "file with spaces.csv": b"x" * 1000,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        with pytest.raises(lambda_module.UnzipError) as excinfo:
            lambda_module.lambda_handler(
                {"bucket": "b", "incoming_key": "in.zip"},
                None,
            )
    err = str(excinfo.value)
    assert "unsafe CSV filename" in err
    assert "file with spaces.csv" in err


def test_handler_normalizes_backslash_traversal(lambda_module):
    """Review item 2 (backslash case): `..\\evil.csv` would NOT be
    split by `split('/')` on Linux — the whole string would be the
    "basename". The Lambda must normalize backslashes to forward
    slashes before splitting so basename = `evil.csv`. Confirms the
    backslash case behaves the same as the forward-slash case."""
    zip_bytes = _build_zip(
        {
            "..\\evil.csv": b"x" * 500,
        }
    )

    fake_s3 = MagicMock()
    fake_s3.get_object.return_value = {"Body": io.BytesIO(zip_bytes)}

    with patch.object(lambda_module, "s3_client", fake_s3):
        result = lambda_module.lambda_handler(
            {"bucket": "b", "incoming_key": "in.zip"},
            None,
        )

    # After backslash-normalization + split, basename is `evil.csv`
    # → safe and uploaded under unzipped/. Critically: NOT escaped.
    assert result["csv_filename"] == "evil.csv"
    assert result["unzipped_key"] == "vdem-staging/unzipped/evil.csv"
    assert "\\" not in result["unzipped_key"]
    assert ".." not in result["unzipped_key"]


def test_handler_safe_regex_accepts_normal_vdem_filenames(lambda_module):
    """Sanity: real V-Dem filenames (with + and -) must pass the
    regex. Catches an over-tightened regex that would reject real
    data on a legitimate upload."""
    real_v_dem_names = [
        "V-Dem-CY-Full+Others-v15.csv",
        "V-Dem-CY-Full+Others-v16.csv",
        "vdem.csv",
        "data_v15.csv",
        "data.csv",
        "DATA.CSV",  # case-insensitive extension
    ]
    for name in real_v_dem_names:
        assert lambda_module.SAFE_CSV_FILENAME_REGEX.match(name), f"regex rejected legitimate V-Dem filename: {name!r}"
