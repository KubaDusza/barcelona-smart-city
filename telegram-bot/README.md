# Telegram Bot + Amazon Bedrock Lambda

This directory contains the AWS Lambda function code for a Telegram bot that interacts with Amazon Bedrock (Nova Lite model) and an external Model Context Protocol (MCP) server.

## Resources Needed to Deploy

To successfully deploy and run this Lambda function, you will need the following resources and configurations:

### 1. AWS Lambda Function
*   **Runtime:** Python 3.9, 3.10, 3.11, or 3.12.
*   **Handler:** `lambda_function.lambda_handler`
*   **Timeout:** Increase the default timeout (e.g., to 30-60 seconds) to allow sufficient time for Bedrock inference and MCP server network calls.
*   **Deployment Package:** You must package the code along with its dependencies. 
    *   Run `pip install -r requirements.txt -t .` inside the folder before zipping.
    *   Zip the contents of this folder and upload it to the Lambda function.

### 2. IAM Role Permissions
The Lambda function's execution role needs the following permissions attached:
*   **Basic Execution:** `AWSLambdaBasicExecutionRole` (for writing logs to CloudWatch).
*   **Amazon Bedrock Access:** Permission to invoke the Nova Lite model.
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock:Converse",
                "Resource": "arn:aws:bedrock:eu-north-1::foundation-model/eu.amazon.nova-lite-v1:0"
            }
        ]
    }
    ```

### 3. API API Gateway or Lambda Function URL
To receive updates from Telegram, the Lambda function needs a public HTTP endpoint.
*   You can set up an **HTTP API via API Gateway** with a `POST` route pointing to this Lambda function.
*   Alternatively, enable a **Lambda Function URL** (often simpler for webhooks).

### 4. Telegram Bot & Webhook Configuration
*   **Bot Token:** You need a Telegram Bot Token (obtained from [@BotFather](https://t.me/BotFather)). *(Note: It is currently hardcoded in `lambda_function.py`. For security, it is highly recommended to move this to an AWS Environment Variable or AWS Secrets Manager).*
*   **Set Webhook:** Once your AWS endpoint is ready, register it with Telegram by making a GET request to:
    `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<YOUR_AWS_ENDPOINT_URL>`

### 5. External MCP Server
*   The code interacts with an external MCP server deployed at `https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp`.
*   Ensure this endpoint is active and accessible from the AWS region where your Lambda is deployed.
