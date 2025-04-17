# usage example

import requests


# this is the entry point that will be used by aws lambda 
def handler(event, context):
    response = requests.get("https://jsonplaceholder.typicode.com/todos/1")

    return {"statusCode": 200, "body": response.json()}