#!/usr/bin/env python3
"""Create and empty the LocalStack bucket used by CLI integration tests."""
import os

import boto3


def prepare_bucket(client, bucket, region):
    arguments = {"Bucket": bucket}
    if region != "us-east-1":
        arguments["CreateBucketConfiguration"] = {"LocationConstraint": region}
    client.create_bucket(**arguments)
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            response = client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            if response.get("Errors"):
                raise RuntimeError(f"failed to empty integration-test bucket: {response['Errors']}")


def main():
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    client = boto3.client(
        "s3",
        endpoint_url=os.environ.get("QW_S3_ENDPOINT", "http://localhost:4566"),
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    prepare_bucket(client, "quickwit-integration-tests", region)


if __name__ == "__main__":
    main()
