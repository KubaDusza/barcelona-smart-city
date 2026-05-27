import json
import urllib3
import boto3

BOT_TOKEN = ""

def sendReply(chat_id, message):
    reply = {"chat_id": chat_id, "text": message}
    http = urllib3.PoolManager()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    encoded_data = json.dumps(reply).encode('utf-8')
    http.request('POST', url, body=encoded_data, headers={'Content-Type': 'application/json'})
    print(f"*** Reply : {encoded_data}")


def ask_bedrock(prompt):
    bedrock = boto3.client('bedrock-runtime', region_name='eu-north-1')
    model_id = 'eu.amazon.nova-lite-v1:0' 
    
    # Your FastMCP Lambda URL
    mcp_url = "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"
    http = urllib3.PoolManager()
    
    # 1. Fetch tools directly via JSON-RPC
    # Provide a payload requesting the tools using the JSON-RPC protocol
    tools_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    
    try:
        req = http.request('POST', mcp_url, body=json.dumps(tools_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        response_data = json.loads(req.data.decode('utf-8'))
        tools_list = response_data.get('result', {}).get('tools', [])
    except Exception as e:
        print(f"Failed to fetch tools: {e}")
        return "Sorry, I lost connection to my tools."

    # Convert MCP tools to Bedrock tool config
    bedrock_tools = []
    for mcp_tool in tools_list:
        bedrock_tools.append({
            "toolSpec": {
                "name": mcp_tool["name"],
                "description": mcp_tool.get("description", "No description"),
                "inputSchema": {
                    "json": mcp_tool["inputSchema"]
                }
            }
        })
        
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    
    # 2. Ask Bedrock
    response = bedrock.converse(
        modelId=model_id,
        messages=messages,
        toolConfig={"tools": bedrock_tools} if bedrock_tools else None
    )
    
    output_msg = response['output']['message']
    
    # 3. Did Bedrock want to call a tool?
    if any('toolUse' in content for content in output_msg['content']):
        tool_use = next(c['toolUse'] for c in output_msg['content'] if 'toolUse' in c)
        tool_name = tool_use['name']
        tool_input = tool_use['input']
        
        # 4. Execute the tool on the MCP server via JSON-RPC
        call_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": tool_input
            }
        }
        
        try:
            req = http.request('POST', mcp_url, body=json.dumps(call_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            call_response_data = json.loads(req.data.decode('utf-8'))
            tool_content = call_response_data.get('result', {}).get('content', [{"text": "Success"}])
            tool_result_text = tool_content[0].get('text', str(tool_content))
            is_error = call_response_data.get('result', {}).get('isError', False)
        except Exception as e:
            tool_result_text = f"Error executing tool: {e}"
            is_error = True
            
        # Format the result back for Bedrock
        messages.append(output_msg) # Append the assistant's request
        messages.append({
            "role": "user",
            "content": [{
                "toolResult": {
                    "toolUseId": tool_use['toolUseId'],
                    "content": [{"text": tool_result_text}],
                    "status": "error" if is_error else "success"
                }
            }]
        })
        
        # Ask Bedrock to summarize the tool result
        final_response = bedrock.converse(
            modelId=model_id,
            messages=messages,
            toolConfig={"tools": bedrock_tools}
        )
        return final_response['output']['message']['content'][0]['text']
    
    return output_msg['content'][0]['text']


def lambda_handler(event, context):
    body = json.loads(event['body'])
    chat_id = body['message']['chat']['id']
    message_text = body['message']['text'] if 'text' in body['message'] else '<not available>'

    if message_text != '<not available>':
        # async wrapper is no longer needed
        reply_message = ask_bedrock(message_text)
    else:
        reply_message = "I am a text bot. Please send me a text message."

    sendReply(chat_id, reply_message)

    return {
        'statusCode': 200,
        'body': json.dumps('Message processed successfully')
    }