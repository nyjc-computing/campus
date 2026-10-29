#!/usr/bin/env python3
"""Tests for campus.storage.objects backends and the bucket factory.

Covers the local filesystem backend, the Railway S3 backend (against a
stubbed boto3 client), and get_bucket() backend selection, including
credential resolution from environment variables and the deployment vault.
"""

import io
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from campus.common import env
from campus.storage import errors as storage_errors
from campus.storage.objects import get_bucket
from campus.storage.objects.backend import railway as railway_backend
from campus.storage.objects.backend.local import LocalBucket
from campus.storage.objects.backend.railway import RailwayBucket
from campus.storage.objects.interface import BucketInterface, ObjectMetadata

# Ensure test mode is on before any test touches the bucket factory
env.set('STORAGE_MODE', "1")


class _BotoError(Exception):
    """botocore-style client error carrying an S3 error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


_CREDENTIALS = {
    "BUCKET": "real-bucket-id",
    "ENDPOINT": "https://s3.example",
    "ACCESS_KEY_ID": "key-id",
    "SECRET_ACCESS_KEY": "secret-key",
}


def _pop_credential_vars():
    """Remove all bucket credential vars from os.environ."""
    for var in railway_backend.CREDENTIAL_VARS + railway_backend.OPTIONAL_VARS:
        os.environ.pop(var, None)


class TestLocalBucket(unittest.TestCase):
    """Test the local filesystem bucket backend."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmpdir.cleanup)
        cls.bucket = LocalBucket("test-bucket", base_path=cls._tmpdir.name)

    def test_implements_bucket_interface(self):
        self.assertIsInstance(self.bucket, BucketInterface)

    def test_put_get_roundtrip(self):
        self.bucket.put("dir/file.txt", b"hello")
        self.assertEqual(self.bucket.get("dir/file.txt"), b"hello")

    def test_get_missing_raises_not_found(self):
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get("missing.txt")

    def test_exists(self):
        self.assertFalse(self.bucket.exists("maybe.txt"))
        self.bucket.put("maybe.txt", b"x")
        self.assertTrue(self.bucket.exists("maybe.txt"))

    def test_delete_removes_object_and_metadata(self):
        self.bucket.put("gone.txt", b"x", {"kind": "temp"})
        self.bucket.delete("gone.txt")
        self.assertFalse(self.bucket.exists("gone.txt"))
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get("gone.txt")
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get_metadata("gone.txt")

    def test_delete_missing_raises_not_found(self):
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.delete("never-existed.txt")

    def test_list_prefix_and_limit(self):
        for key in ("lst/a/1.txt", "lst/a/2.txt", "lst/b/3.txt"):
            self.bucket.put(key, b"x")
        keys = self.bucket.list(prefix="lst/a/")
        self.assertEqual(sorted(keys), ["lst/a/1.txt", "lst/a/2.txt"])
        limited = self.bucket.list(prefix="lst/", limit=2)
        self.assertEqual(len(limited), 2)
        self.assertTrue(all(k.startswith("lst/") for k in limited))

    def test_metadata_files_hidden_from_list(self):
        self.bucket.put("hide/withmeta.txt", b"x", {"kind": "note"})
        self.assertEqual(self.bucket.list(prefix="hide/"), ["hide/withmeta.txt"])

    def test_get_metadata(self):
        self.bucket.put("meta/plain.txt", b"12345", {"content-type": "text/plain"})
        meta = self.bucket.get_metadata("meta/plain.txt")
        self.assertIsInstance(meta, ObjectMetadata)
        self.assertEqual(meta.size, 5)
        self.assertEqual(meta.content_type, "text/plain")
        self.assertIsNotNone(meta.last_modified)
        self.assertTrue(meta.etag)
        self.assertIn("_uploaded_at", meta.custom)

    def test_put_content_type_roundtrips_without_metadata(self):
        self.bucket.put("ct/plain.txt", b"12345", content_type="text/plain")
        meta = self.bucket.get_metadata("ct/plain.txt")
        self.assertEqual(meta.content_type, "text/plain")
        self.assertIn("_uploaded_at", meta.custom)

    def test_put_content_type_overrides_metadata_key(self):
        self.bucket.put(
            "ct/mixed.txt", b"x", {"content-type": "image/png"},
            content_type="application/pdf",
        )
        self.assertEqual(
            self.bucket.get_metadata("ct/mixed.txt").content_type,
            "application/pdf",
        )

    def test_put_does_not_mutate_caller_metadata(self):
        caller_metadata = {"kind": "note"}
        self.bucket.put("ct/mutate.txt", b"x", caller_metadata)
        self.assertEqual(caller_metadata, {"kind": "note"})
        meta = self.bucket.get_metadata("ct/mutate.txt")
        self.assertEqual(meta.custom["kind"], "note")
        self.assertIn("_uploaded_at", meta.custom)

    def test_copy_preserves_data_and_metadata(self):
        self.bucket.put("cp/src.txt", b"data", {"kind": "orig"})
        self.bucket.copy("cp/src.txt", "cp/dst.txt")
        self.assertEqual(self.bucket.get("cp/dst.txt"), b"data")
        self.assertTrue(self.bucket.exists("cp/src.txt"))
        self.assertEqual(self.bucket.get_metadata("cp/dst.txt").custom["kind"], "orig")

    def test_copy_missing_source_raises_not_found(self):
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.copy("cp/nope.txt", "cp/dst.txt")

    def test_path_traversal_rejected(self):
        with self.assertRaises(storage_errors.StorageError):
            self.bucket.put("../escape.txt", b"x")
        with self.assertRaises(storage_errors.StorageError):
            self.bucket.get("~/home.txt")

    def test_get_url_local_is_file_url(self):
        self.bucket.put("url/file.txt", b"x")
        self.assertTrue(self.bucket.get_url("url/file.txt").startswith("file://"))
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get_url("url/missing.txt")


class TestRailwayBucket(unittest.TestCase):
    """Test the Railway S3 backend against a stubbed boto3 client."""

    def setUp(self):
        patcher = mock.patch.object(railway_backend, "boto3")
        self.mock_boto3 = patcher.start()
        self.addCleanup(patcher.stop)
        self.s3 = mock.MagicMock()
        self.mock_boto3.client.return_value = self.s3
        self.bucket = RailwayBucket("ns", credentials=dict(_CREDENTIALS))

    def test_client_creation_deferred_until_use(self):
        self.mock_boto3.client.assert_not_called()
        self.bucket.exists("x")
        self.mock_boto3.client.assert_called_once()
        kwargs = self.mock_boto3.client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], "https://s3.example")
        self.assertEqual(kwargs["aws_access_key_id"], "key-id")
        self.assertEqual(kwargs["config"].region_name, "auto")

    def test_explicit_credentials_override_environment(self):
        with mock.patch.dict(os.environ, {"BUCKET": "env-bucket"}):
            bucket = RailwayBucket("ns", credentials=dict(_CREDENTIALS))
        bucket.put("k", b"v")
        self.assertEqual(
            self.s3.put_object.call_args.kwargs["Bucket"], "real-bucket-id"
        )

    def test_put_namespaces_key_and_prefixes_metadata(self):
        self.bucket.put("dir/file.txt", b"data", {"kind": "txt"})
        kwargs = self.s3.put_object.call_args.kwargs
        self.assertEqual(kwargs["Bucket"], "real-bucket-id")
        self.assertEqual(kwargs["Key"], "ns/dir/file.txt")
        self.assertEqual(kwargs["Body"], b"data")
        self.assertEqual(kwargs["Metadata"], {"x-amz-meta-kind": "txt"})

    def test_put_without_metadata_omits_metadata_kwarg(self):
        self.bucket.put("file.txt", b"data")
        kwargs = self.s3.put_object.call_args.kwargs
        self.assertNotIn("Metadata", kwargs)
        self.assertNotIn("ContentType", kwargs)

    def test_put_sets_content_type(self):
        self.bucket.put("file.pdf", b"data", content_type="application/pdf")
        kwargs = self.s3.put_object.call_args.kwargs
        self.assertEqual(kwargs["ContentType"], "application/pdf")
        self.assertNotIn("Metadata", kwargs)

    def test_get_returns_body_bytes(self):
        self.s3.get_object.return_value = {"Body": io.BytesIO(b"bytes")}
        self.assertEqual(self.bucket.get("file.txt"), b"bytes")
        self.assertEqual(
            self.s3.get_object.call_args.kwargs["Key"], "ns/file.txt"
        )

    def test_error_mapping(self):
        self.s3.get_object.side_effect = _BotoError("NoSuchKey")
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get("file.txt")
        self.s3.get_object.side_effect = _BotoError("404")
        with self.assertRaises(storage_errors.NotFoundError):
            self.bucket.get("file.txt")
        self.s3.get_object.side_effect = _BotoError("AccessDenied")
        with self.assertRaises(storage_errors.StorageError):
            self.bucket.get("file.txt")

    def test_exists(self):
        self.assertTrue(self.bucket.exists("file.txt"))
        self.s3.head_object.side_effect = _BotoError("NoSuchKey")
        self.assertFalse(self.bucket.exists("file.txt"))
        self.s3.head_object.side_effect = _BotoError("AccessDenied")
        with self.assertRaises(storage_errors.StorageError):
            self.bucket.exists("file.txt")

    def test_list_pages_and_strips_namespace(self):
        self.s3.list_objects_v2.side_effect = [
            {
                "Contents": [{"Key": "ns/a"}, {"Key": "ns/b/c"}],
                "IsTruncated": True,
                "NextContinuationToken": "tok",
            },
            {"Contents": [{"Key": "ns/d"}], "IsTruncated": False},
        ]
        self.assertEqual(self.bucket.list(), ["a", "b/c", "d"])
        first_call = self.s3.list_objects_v2.call_args_list[0].kwargs
        self.assertEqual(first_call["Prefix"], "ns")

    def test_list_respects_limit(self):
        self.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "ns/a"}, {"Key": "ns/b"}, {"Key": "ns/c"}],
            "IsTruncated": False,
        }
        self.assertEqual(self.bucket.list(limit=2), ["a", "b"])

    def test_list_missing_bucket_returns_empty(self):
        self.s3.list_objects_v2.side_effect = _BotoError("NoSuchBucket")
        self.assertEqual(self.bucket.list(), [])

    def test_get_metadata(self):
        self.s3.head_object.return_value = {
            "ContentLength": 5,
            "LastModified": datetime(2026, 1, 1),
            "ContentType": "text/plain",
            "ETag": '"etag123"',
            "Metadata": {"x-amz-meta-kind": "txt"},
        }
        meta = self.bucket.get_metadata("file.txt")
        self.assertEqual(meta.key, "file.txt")
        self.assertEqual(meta.size, 5)
        self.assertEqual(meta.content_type, "text/plain")
        self.assertEqual(meta.etag, "etag123")
        self.assertEqual(meta.custom, {"kind": "txt"})

    def test_get_url_passes_bucket_key_expiry(self):
        self.s3.generate_presigned_url.return_value = "https://presigned"
        url = self.bucket.get_url("file.txt", expires_in=60)
        self.assertEqual(url, "https://presigned")
        kwargs = self.s3.generate_presigned_url.call_args.kwargs
        self.assertEqual(kwargs["Params"]["Key"], "ns/file.txt")
        self.assertEqual(kwargs["ExpiresIn"], 60)

    def test_copy_builds_copy_source(self):
        self.bucket.copy("src.txt", "dst.txt")
        kwargs = self.s3.copy_object.call_args.kwargs
        self.assertEqual(
            kwargs["CopySource"],
            {"Bucket": "real-bucket-id", "Key": "ns/src.txt"},
        )
        self.assertEqual(kwargs["Key"], "ns/dst.txt")

    def test_missing_credentials_raise_with_all_names(self):
        with (mock.patch.object(
                  railway_backend, "resolve_credential", return_value=None
              ),
              self.assertRaises(OSError) as cm):
            RailwayBucket("ns")
        for var in railway_backend.CREDENTIAL_VARS:
            self.assertIn(var, str(cm.exception))

    def test_partial_credentials_raise_for_missing_keys(self):
        partial = {"BUCKET": "b", "ENDPOINT": "https://s3"}
        with (mock.patch.object(
                  railway_backend,
                  "resolve_credential",
                  side_effect=lambda name: partial.get(name),
              ),
              self.assertRaises(OSError) as cm):
            RailwayBucket("ns")
        self.assertIn("ACCESS_KEY_ID", str(cm.exception))
        self.assertIn("SECRET_ACCESS_KEY", str(cm.exception))


class TestCredentialResolution(unittest.TestCase):
    """Test credential resolution from environment and vault sources."""

    def test_environment_takes_precedence_over_vault(self):
        fake_getsecret = mock.MagicMock(return_value="vault-value")
        with (mock.patch.dict(os.environ, {"BUCKET": "env-value"}),
              mock.patch.object(env, "_getsecret_func", fake_getsecret)):
            self.assertEqual(
                railway_backend.resolve_credential("BUCKET"), "env-value"
            )
        fake_getsecret.assert_not_called()

    def test_vault_used_when_env_missing(self):
        fake_getsecret = mock.MagicMock(return_value="vault-value")
        with (mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", fake_getsecret)):
            _pop_credential_vars()
            self.assertEqual(
                railway_backend.resolve_credential("BUCKET"), "vault-value"
            )
        fake_getsecret.assert_called_once_with("BUCKET")

    def test_unconfigured_returns_none(self):
        with (mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", None)):
            _pop_credential_vars()
            self.assertIsNone(railway_backend.resolve_credential("ENDPOINT"))

    def test_resolve_credentials_none_when_unconfigured(self):
        with (mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", None)):
            _pop_credential_vars()
            self.assertIsNone(railway_backend.resolve_credentials())


class TestGetBucketFactory(unittest.TestCase):
    """Test get_bucket() backend selection."""

    def test_test_mode_uses_local(self):
        with mock.patch.dict(os.environ, {"STORAGE_MODE": "1"}):
            self.assertIsInstance(get_bucket("uploads"), LocalBucket)

    def test_factory_returns_interface_instance(self):
        with mock.patch.dict(os.environ, {"STORAGE_MODE": "1"}):
            self.assertIsInstance(get_bucket("uploads"), BucketInterface)

    def test_dev_with_env_credentials_uses_railway(self):
        env_vars = {"STORAGE_MODE": "0", "ENV": "development", **_CREDENTIALS}
        with (mock.patch.dict(os.environ, env_vars),
              mock.patch.object(env, "_getsecret_func", None)):
            bucket = get_bucket("uploads")
        self.assertIsInstance(bucket, RailwayBucket)
        self.assertEqual(bucket._bucket_name, "real-bucket-id")

    def test_dev_without_credentials_uses_local(self):
        with (mock.patch.dict(os.environ,
                              {"STORAGE_MODE": "0", "ENV": "development"}),
              mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", None)):
            _pop_credential_vars()
            bucket = get_bucket("uploads")
        self.assertIsInstance(bucket, LocalBucket)

    def test_dev_with_vault_credentials_uses_railway(self):
        fake_getsecret = mock.MagicMock(
            side_effect=lambda name: _CREDENTIALS.get(name)
        )
        with (mock.patch.dict(os.environ,
                              {"STORAGE_MODE": "0", "ENV": "development"}),
              mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", fake_getsecret)):
            _pop_credential_vars()
            bucket = get_bucket("uploads")
        self.assertIsInstance(bucket, RailwayBucket)
        self.assertEqual(bucket._bucket_name, "real-bucket-id")

    def test_staging_uses_railway(self):
        env_vars = {"STORAGE_MODE": "0", "ENV": "staging", **_CREDENTIALS}
        with mock.patch.dict(os.environ, env_vars):
            bucket = get_bucket("uploads")
        self.assertIsInstance(bucket, RailwayBucket)

    def test_staging_without_credentials_raises(self):
        with (mock.patch.dict(os.environ,
                              {"STORAGE_MODE": "0", "ENV": "staging"}),
              mock.patch.dict(os.environ),
              mock.patch.object(env, "_getsecret_func", None)):
            _pop_credential_vars()
            with self.assertRaises(OSError):
                get_bucket("uploads")


if __name__ == "__main__":
    unittest.main()
