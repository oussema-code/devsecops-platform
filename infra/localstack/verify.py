"""Run inside the LocalStack container after OpenTofu apply."""
import json
import time
import uuid
import boto3


def client(service):
    return boto3.client(service, endpoint_url="http://127.0.0.1:4566", region_name="us-east-1",
                        aws_access_key_id="test", aws_secret_access_key="test")


def wait(description, check, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            print("PASS", description, flush=True)
            return
        time.sleep(3)
    raise RuntimeError("Timed out waiting for " + description)


def main():
    assert client("sts").get_caller_identity()["Account"] == "000000000000"
    marker = "drill-" + uuid.uuid4().hex
    bucket, key = "boutique-lab-input", "imports/" + marker + ".csv"
    queue = client("sqs")
    work = queue.get_queue_url(QueueName="boutique-work")["QueueUrl"]
    dead = queue.get_queue_url(QueueName="boutique-dead")["QueueUrl"]
    table = client("dynamodb")
    s3 = client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=f"name,email\n{marker},demo@example.invalid\n".encode())
    body = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
    queue.send_message(QueueUrl=work, MessageBody=json.dumps(body))
    def processed_twice():
        events = client("logs").filter_log_events(logGroupName="/aws/lambda/boutique-sample-worker",
                                                  filterPattern='"' + marker + '"')["events"]
        return len({e["eventId"] for e in events if "Received record:" in e["message"]}) >= 2
    wait("two deliveries processed", processed_twice)
    item = table.get_item(TableName="employeeInfoNew", Key={"name": {"S": marker}}, ConsistentRead=True)["Item"]
    assert item == {"name": {"S": marker}, "email": {"S": "demo@example.invalid"}}
    print("PASS repeated delivery has the same stored result")
    body["Records"][0]["s3"]["object"]["key"] = "imports/missing-" + marker
    queue.send_message(QueueUrl=work, MessageBody=json.dumps(body))
    def dead_lettered():
        for message in queue.receive_message(QueueUrl=dead, MaxNumberOfMessages=10, VisibilityTimeout=1).get("Messages", []):
            if message["Body"] == json.dumps(body):
                return True
        return False
    wait("poison message redriven to DLQ", dead_lettered, seconds=300)


if __name__ == "__main__":
    main()
