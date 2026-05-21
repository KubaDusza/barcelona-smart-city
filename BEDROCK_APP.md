# Barcelona Smart City — Bedrock Chat App

This document explains what was built, how it works end-to-end, and the decisions made along the way.

---

## What it is

A public web chatbot that answers natural-language questions about Barcelona city conditions — air quality, weather, UV, pollen, Bicing bike availability, and transit — using live data. When you ask "is today a good day to cycle?", the agent calls four data tools in one turn and synthesises a real answer.

Live URL: `https://dhioxm566jvi3.cloudfront.net`

---

## Architecture

```
Browser
  │
  │  HTTPS (GET)
  ▼
CloudFront  ──────────────────────────►  S3 bucket (static HTML/JS)
  │
  │  HTTPS (POST /chat)
  ▼
API Gateway (HTTP API, eu-west-1)
  │
  ▼
Lambda: smart-city-chat  (Python 3.12, 60s timeout)
  │
  ├──  bedrock-runtime.invoke_model  ──►  Claude Haiku (eu.anthropic.claude-haiku-4-5)
  │         agentic loop: Claude decides which tools to call, in a loop
  │
  └──  urllib HTTP POST  ──►  MCP server (API Gateway + Lambda, eu-west-1)
                                  └──  DynamoDB reads / live API calls
```

---

## AWS resources created

| Resource | Name / ID | Purpose |
|---|---|---|
| Lambda | `smart-city-chat` | Chat handler — runs the agentic loop |
| Lambda execution role | `smart-city-chat-role` | `bedrock:InvokeModel` + CloudWatch Logs |
| API Gateway (HTTP API) | `386ccled52` | Public HTTPS endpoint for the chat Lambda |
| S3 bucket | `barcelona-smart-city-site-724440691846` | Hosts the static web UI |
| CloudFront distribution | `E2LPOSVMFTXZ34` | CDN + HTTPS for the S3 site |
| AgentCore Gateway | `barcelona-smart-city-xwyxovrhex` | Managed MCP proxy (described below) |
| IAM role | `agentcore-gateway-role` | Assumed by AgentCore Gateway to call API Gateway |

All resources are in `eu-west-1` except CloudFront (global) and the AgentCore Gateway IAM setup (global).

The `smart_city` IAM user was consolidated from 9 separate managed policies into one inline policy (`SmartCityAccess`) covering DynamoDB, S3, Lambda, EventBridge, API Gateway, CloudWatch Logs, IAM, CloudFront, and Bedrock. This was necessary because IAM users have a hard limit of 10 attached managed policies.

---

## How MCP is used

The project has an existing MCP server deployed on AWS (Lambda + API Gateway) that exposes 11 tools over JSON-RPC 2.0:

```
https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp
```

The MCP server is stateless — each JSON-RPC request to it is an independent Lambda invocation. This means the chat Lambda can call it with plain HTTP POST requests, without maintaining a persistent connection or session. The full sequence per tool call:

1. `POST /mcp` with `{"method": "initialize", ...}` — required by the MCP protocol
2. `POST /mcp` with `{"method": "tools/call", "params": {"name": "get_weather", "arguments": {}}}` — executes the tool
3. The MCP Lambda reads from DynamoDB (or calls an external API) and returns the result as a JSON-RPC response

The chat Lambda does this for each tool Claude decides to call, inside the agentic loop.

### AgentCore Gateway

During development, AWS Bedrock AgentCore Gateway was also set up as a managed MCP proxy. It auto-discovers tools from the MCP server via `tools/list` and exposes them at a signed URL:

```
https://barcelona-smart-city-xwyxovrhex.gateway.bedrock-agentcore.eu-west-1.amazonaws.com/mcp
```

Setup was done with the AWS CLI:

```bash
# 1. Create gateway
aws bedrock-agentcore-control create-gateway \
  --name barcelona-smart-city \
  --role-arn arn:aws:iam::724440691846:role/agentcore-gateway-role \
  --protocol-type MCP \
  --authorizer-type NONE \
  --region eu-west-1

# 2. Register our existing MCP endpoint as a target
aws bedrock-agentcore-control create-gateway-target \
  --gateway-identifier barcelona-smart-city-xwyxovrhex \
  --name barcelona-mcp-server \
  --target-configuration '{"mcp": {"mcpServer": {"endpoint": "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"}}}' \
  --region eu-west-1

# 3. Sync — gateway calls tools/list on our MCP server and indexes all 11 tools
aws bedrock-agentcore-control synchronize-gateway-targets \
  --gateway-identifier barcelona-smart-city-xwyxovrhex \
  --target-id-list X2ZN1XIFCP \
  --region eu-west-1
```

The chat Lambda currently calls the MCP server directly (simpler, no SigV4 required since the MCP endpoint is unauthenticated). The AgentCore Gateway is available for future use with Bedrock Agents or Strands SDK.

---

## How the agentic loop works

The chat Lambda (`aws/lambdas/chat/lambda_function.py`) implements the loop manually using `bedrock-runtime`:

```
1. Receive user message + conversation history from the frontend
2. Fetch available tools from the MCP server (tools/list, cached in Lambda memory)
3. Call Claude with the user message, conversation history, and tool schemas
4. If Claude responds with stop_reason = "tool_use":
     a. For each tool_use block in the response:
        - Call the MCP server with the tool name and arguments
        - Collect the result
     b. Append the assistant turn + tool results to the message history
     c. Call Claude again — repeat from step 4
5. When Claude responds with stop_reason = "end_turn", return the final text
```

This loop runs up to 8 rounds. In practice, a composite query like "is it a good day to cycle?" triggers 4 tool calls (weather, UV, air quality, pollen) in a single round before Claude synthesises the answer.

The full tool call log (tool name + input + result) is returned to the frontend alongside the text response so the UI can show what happened.

---

## Frontend: expandable agent activity

The web UI (`webapp/index.html`) is a single static HTML file with no build step or dependencies. It uses the Fetch API to POST to the chat endpoint and receives a JSON response:

```json
{
  "response": "Today is a great day to cycle...",
  "tool_calls": [
    {"tool": "barcelona-mcp-server___get_weather", "input": {}, "result": {...}},
    {"tool": "barcelona-mcp-server___get_uv_index", "input": {"lat": 41.39, "lon": 2.17}, "result": {...}}
  ]
}
```

Each tool call is rendered as a collapsible block above the assistant's text reply. The block shows the tool name and, when expanded, the full input and result as syntax-highlighted JSON. The DOM is built entirely with `createElement` / `appendChild` — never `innerHTML +=` — so click event listeners are not lost on re-render.

---

## How the deployment works

### Lambda

Deployed as a zip file via `aws lambda create-function` / `update-function-code`. No dependencies beyond the standard library and `boto3` (pre-installed in the Lambda Python 3.12 runtime). The Lambda is invoked by API Gateway using the `AWS_PROXY` integration with payload format version `2.0`.

### Static site

The S3 bucket has public read access and static website hosting enabled. CloudFront sits in front of it for HTTPS and CDN caching. The HTML is uploaded with `Cache-Control: no-cache, no-store` so that re-deploys are picked up immediately after a CloudFront invalidation.

To redeploy the frontend after changes:

```bash
aws s3 cp webapp/index.html s3://barcelona-smart-city-site-724440691846/index.html \
  --content-type "text/html" --cache-control "no-cache, no-store" --region eu-west-1

aws cloudfront create-invalidation \
  --distribution-id E2LPOSVMFTXZ34 --paths "/*" --region us-east-1
```

To redeploy the chat Lambda after changes:

```bash
cd aws/lambdas/chat
zip -r /tmp/smart-city-chat.zip .
aws lambda update-function-code \
  --function-name smart-city-chat \
  --zip-file fileb:///tmp/smart-city-chat.zip \
  --region eu-west-1
```

---

## Key decisions and what we learned

**The MCP endpoint is unauthenticated.** The existing MCP server (deployed before this app) has no IAM auth on its API Gateway methods. This made it straightforward to call from the chat Lambda without SigV4 signing. For production use, adding `AWS_IAM` auth and SigV4 signing in the Lambda would be the right move.

**AgentCore Gateway needs IAM auth on the MCP endpoint to call it securely.** When we set up the gateway, it connected to our unauthenticated endpoint without issues. But the gateway itself requires SigV4 signing from callers, which means it cannot be called from a browser directly — a backend proxy is always needed.

**Lambda Function URLs hit an account-level block.** The first attempt used a Lambda Function URL (auth type NONE) as the chat API. This returned 403 despite the correct resource policy. Switching to an API Gateway HTTP API resolved it immediately.

**`innerHTML +=` destroys event listeners.** A one-line bug (`div.innerHTML += ""`) caused the expandable tool blocks to not respond to clicks. When you assign to `innerHTML`, the browser serialises the current DOM to HTML and then re-parses it — all JavaScript event listeners attached with `addEventListener` are lost. The fix is to build the DOM with `createElement` and `appendChild` exclusively.

**The IAM 10-managed-policy limit is easy to hit.** The `smart_city` user accumulated 9 managed policies from earlier setup work. Adding Bedrock permissions would have exceeded the limit. The solution was to detach all managed policies and replace them with a single inline policy. Inline policies do not count toward the managed-policy attachment limit.
