import boto3

_resource = None


def get_resource():
    global _resource
    if _resource is None:
        _resource = boto3.resource('dynamodb')
    return _resource


def transact_write(items: list[dict]):
    get_resource().meta.client.transact_write_items(TransactItems=items)
