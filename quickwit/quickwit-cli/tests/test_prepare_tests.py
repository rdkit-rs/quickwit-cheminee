import unittest

import boto3
from botocore.stub import Stubber

from prepare_tests import prepare_bucket


class BucketPreparationTests(unittest.TestCase):
    def setUp(self):
        self.client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.bucket = "quickwit-integration-tests"

    def test_create_and_delete_all_pages(self):
        self.stub.add_response("create_bucket", {}, {"Bucket": self.bucket})
        self.stub.add_response("list_objects_v2", {"Contents": [{"Key": "first"}], "IsTruncated": True, "NextContinuationToken": "next"}, {"Bucket": self.bucket})
        self.stub.add_response("delete_objects", {}, {"Bucket": self.bucket, "Delete": {"Objects": [{"Key": "first"}]}})
        self.stub.add_response("list_objects_v2", {"Contents": [{"Key": "second"}], "IsTruncated": False}, {"Bucket": self.bucket, "ContinuationToken": "next"})
        self.stub.add_response("delete_objects", {}, {"Bucket": self.bucket, "Delete": {"Objects": [{"Key": "second"}]}})
        prepare_bucket(self.client, self.bucket, "us-east-1")
        self.stub.assert_no_pending_responses()

    def test_empty_bucket_in_another_region(self):
        self.stub.add_response("create_bucket", {}, {"Bucket": self.bucket, "CreateBucketConfiguration": {"LocationConstraint": "eu-west-1"}})
        self.stub.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": self.bucket})
        prepare_bucket(self.client, self.bucket, "eu-west-1")
        self.stub.assert_no_pending_responses()

    def test_deletion_errors_fail(self):
        self.stub.add_response("create_bucket", {}, {"Bucket": self.bucket})
        self.stub.add_response("list_objects_v2", {"Contents": [{"Key": "denied"}], "IsTruncated": False}, {"Bucket": self.bucket})
        self.stub.add_response("delete_objects", {"Errors": [{"Key": "denied", "Code": "AccessDenied"}]}, {"Bucket": self.bucket, "Delete": {"Objects": [{"Key": "denied"}]}})
        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            prepare_bucket(self.client, self.bucket, "us-east-1")


if __name__ == "__main__":
    unittest.main()
